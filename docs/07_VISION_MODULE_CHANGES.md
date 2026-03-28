# Vision Module: Frame Storage & Track Lifecycle

## Overview

The vision module is the **entry point** of the entire pipeline — all data originates here. In addition to emitting JSON metadata to Pulsar, it saves keyframes to GCS and writes track lifecycle events to PostgreSQL.

---

## 1. Module Architecture

```
vision/main.py
  → yolo_detector.py       (detect objects)
  → yolo_tracker_*.py      (track objects)
  → pulsar_emitter.py      (emit JSON metadata → Pulsar)
  → frame_saver.py         (save keyframes → GCS)
  → track_lifecycle.py     (write track events → PostgreSQL)
  → visualizer.py          (render on screen)
```

**Outputs per frame:**
1. **JSON metadata** → Pulsar (every frame, ~30 FPS)
2. **Keyframe JPEG** → GCS (once per second)
3. **Track events** → PostgreSQL (on track start/end, and sampled positions)

---

## 2. Components

### 2.1 `vision/emit/frame_saver.py`

```python
from google.cloud import storage
import cv2
from datetime import datetime


class FrameSaver:
    """
    Saves keyframes to GCS at SAVE_INTERVAL seconds.
    Does not save every frame (30 FPS) — saves 1 frame per second only.
    """

    def __init__(self, bucket_name: str = "rva-frames", save_interval: int = 1):
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)
        self.save_interval = save_interval  # seconds
        self._last_save: float = 0.0

    def should_save(self, current_time: float) -> bool:
        return (current_time - self._last_save) >= self.save_interval

    def save_frame(self, frame, camera_id: str, timestamp: str) -> str | None:
        """
        Save frame to GCS. Returns gs:// path or None if interval not reached.
        """
        import time
        now = time.monotonic()
        if not self.should_save(now):
            return None

        self._last_save = now

        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        blob_name = (
            f"{dt.strftime('%Y-%m-%d')}/{camera_id}/"
            f"{dt.strftime('%H')}/{dt.strftime('%H-%M-%S')}.jpg"
        )

        # Encode JPEG (quality 80 — sufficient for review, not too large)
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])

        blob = self.bucket.blob(blob_name)
        blob.upload_from_string(buffer.tobytes(), content_type="image/jpeg")

        return f"gs://{self.bucket.name}/{blob_name}"
```

**Storage estimate:**
```
1 frame/second × 100KB/frame × 3600s = 360 MB/hour/camera
× 24 hours = 8.6 GB/day/camera (with 7-day lifecycle = 60 GB max)
```

---

### 2.2 `vision/emit/track_lifecycle.py`

```python
import asyncpg
from datetime import datetime, timezone
from typing import Dict, Optional


class TrackLifecycleManager:
    """
    Tracks the lifecycle of each track_id.
    Writes to PostgreSQL when a track appears or disappears.
    """

    TRACK_TIMEOUT_SEC = 30  # track missing for > 30s is treated as track_end

    def __init__(self, db_pool: asyncpg.Pool):
        self.pool = db_pool
        # {(camera_id, track_id): last_seen_timestamp}
        self._active_tracks: Dict[tuple, datetime] = {}
        self._sample_counter: Dict[tuple, int] = {}

    async def on_detection(
        self,
        camera_id: str,
        track_id: int,
        center_x: int,
        center_y: int,
        confidence: float,
        timestamp: str,
        frame_path: Optional[str] = None,
    ):
        key = (camera_id, track_id)
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

        if key not in self._active_tracks:
            # New track — write track_start
            await self._write_event(
                camera_id, track_id, "track_start",
                ts, center_x, center_y, confidence, frame_path
            )
            self._active_tracks[key] = ts
            self._sample_counter[key] = 0

        # Position sample every 1 second
        self._sample_counter[key] += 1
        elapsed = (ts - self._active_tracks[key]).total_seconds()
        if elapsed >= 1.0:
            await self._write_event(
                camera_id, track_id, "position_sample",
                ts, center_x, center_y, confidence, frame_path=None
            )
            self._active_tracks[key] = ts

    async def check_timeouts(self, current_time: datetime):
        """Call every 5 seconds to detect track_end events."""
        expired = [
            key for key, last_seen in self._active_tracks.items()
            if (current_time - last_seen).total_seconds() > self.TRACK_TIMEOUT_SEC
        ]
        for key in expired:
            camera_id, track_id = key
            await self._write_event(
                camera_id, track_id, "track_end",
                self._active_tracks[key], None, None, None, frame_path=None
            )
            del self._active_tracks[key]
            del self._sample_counter[key]

    async def _write_event(
        self, camera_id, track_id, event_type,
        timestamp, cx, cy, conf, frame_path
    ):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO core.track_events
                (camera_id, track_id, event_type, timestamp,
                 center_x, center_y, confidence, frame_path)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT DO NOTHING
            """, camera_id, track_id, event_type,
                timestamp, cx, cy, conf, frame_path)
```

---

## 3. Integration in `vision/main.py`

```python
# vision/main.py — initialization
from emit.frame_saver import FrameSaver
from emit.track_lifecycle import TrackLifecycleManager

frame_saver = FrameSaver(
    bucket_name=settings.GCS_FRAMES_BUCKET,
    save_interval=1,  # 1 frame per second
)

# TrackLifecycleManager requires an asyncpg pool — initialize before main loop
track_mgr = TrackLifecycleManager(db_pool)

# In the main loop:
for frame_index, (frame, detections) in enumerate(tracker.stream()):
    capture_ts = datetime.now(timezone.utc).isoformat()

    # 1. Emit metadata → Pulsar (every frame)
    emitter.emit_frame(frame_index, detections, capture_ts)

    # 2. Save keyframe → GCS (once per second)
    frame_path = frame_saver.save_frame(frame, settings.CAMERA_ID, capture_ts)

    # 3. Track lifecycle events → PostgreSQL
    for det in detections:
        await track_mgr.on_detection(
            camera_id=settings.CAMERA_ID,
            track_id=det["track_id"],
            center_x=det["centroid"]["x"],
            center_y=det["centroid"]["y"],
            confidence=det["conf"],
            timestamp=capture_ts,
            frame_path=frame_path,  # None if no frame was saved this cycle
        )

    # 4. Check track timeouts every 5 seconds
    if frame_index % (settings.FPS * 5) == 0:
        await track_mgr.check_timeouts(datetime.now(timezone.utc))
```

---

## 4. Environment Variables

### `vision/.env`:

```env
# Existing
MODEL_NAME=yolo11l.pt
VIDEO_PATH=video/0000000448100010000.mp4
TRACKER_TYPE=botsort
CLASS_FILTER=[0]
CONF_THRES=0.25
STORE_ID=store_01
CAMERA_ID=cam_01
STREAM_ID=stream_01
PULSAR_SERVICE_URL=pulsar://pulsar-broker:6650
PULSAR_TOPIC=persistent://retail/metadata/events

# GCS for frame storage
GCS_PROJECT_ID=my-gcp-project
GCS_FRAMES_BUCKET=rva-frames
GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcs-service-account.json
FRAME_SAVE_INTERVAL=1  # seconds

# PostgreSQL for track events
POSTGRES_DSN=postgresql://rva:rva_secret@postgres:5432/rva_metadata
```

---

## 5. Data Flow

```
Camera/Video
    │
    ▼
YOLO11 + BoTSORT
    │
    ├── detections: [{track_id, bbox, conf, centroid}, ...]
    │
    ├─────────────────────────────────────────────────────┐
    │                                                     │
    ▼                                                     ▼
PulsarEmitter                                      FrameSaver
(every frame, ~30 FPS)                            (every 1 second)
    │                                                     │
    ▼                                                     ▼
Pulsar Topic                                        GCS
persistent://retail/                              gs://rva-frames/
  metadata/events                                {date}/{cam}/{hh-mm-ss}.jpg
    │
    ├──────────────────────┐
    │                      │
    ▼                      ▼
Flink Fast Path      Flink Slow Path
(CEP alerting)       (Medallion ETL)
    │                      │
    ▼                      ▼
Redis                  Iceberg
                      (Bronze→Silver→Gold)

TrackLifecycleManager (runs in vision process)
    │
    ▼
PostgreSQL: core.track_events
(track_start, position_sample, track_end)
```

---

## 6. Deployment Checklist

- [ ] Create `vision/emit/frame_saver.py`
- [ ] Create `vision/emit/track_lifecycle.py`
- [ ] Update `vision/main.py` to integrate both modules
- [ ] Add environment variables to `vision/.env`
- [ ] Add `google-cloud-storage`, `asyncpg` to `vision/setup.txt`
- [ ] Create GCS bucket `rva-frames` with 7-day lifecycle policy
- [ ] Run SQL migration to create `core.track_events` table
- [ ] Verify: frame saved to GCS after 1 second
- [ ] Verify: `track_start` event appears in PostgreSQL when a new person is detected
- [ ] Verify: `track_end` event appears after 30 seconds without signal

---

## Related Documents

- [02_ARCHITECTURE_IMPROVED.md](./02_ARCHITECTURE_IMPROVED.md) - Dual-Path Architecture
- [03_DATABASE_SCHEMA.md](./03_DATABASE_SCHEMA.md) - Schema for `core.track_events`
- [05_ACTION_PLAN.md](./05_ACTION_PLAN.md) - Implementation steps
