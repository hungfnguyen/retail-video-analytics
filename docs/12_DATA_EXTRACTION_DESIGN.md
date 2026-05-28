# Vision Module — Data Extraction Design

## 1. Overview

Vision module produces **3 output planes** from the same camera source, nhưng chúng nên được xem là ba luồng dữ liệu tách biệt:

```
                         ┌─── Plane 1: Metadata JSON ──→ Pulsar ──→ Flink ──→ Iceberg
Frame ──→ YOLO+BoTSORT ──┼─── Plane 2: Sampled JPEG ──→ S3
                         └─── Plane 3: Alert Clip ────→ S3
```

| Plane | Format | Destination | Size/frame | Frequency | Purpose |
|-------|--------|-------------|-----------|-----------|---------|
| 1. Metadata | JSON (~2KB) | Pulsar topic | 2 KB | Every frame (25 fps) | Stream analytics, real-time metrics |
| 2. Sampled frame | JPEG (~150KB) | S3 `frames/` | 150 KB | 1 fps per camera | Visual verification, debugging, evidence |
| 3. Alert clip | MP4 (~5MB) | S3 `clips/` | 5 MB | On alert trigger | Incident replay, stakeholder review |

**Why 3 planes, not 1?**

- Pushing raw frames (200KB × 25fps) through Pulsar is not practical — Pulsar is designed for small event messages, not binary blobs.
- Analytics engines (Flink, Trino) operate on structured metadata, not pixel data.
- Sampled frames provide visual ground truth without saturating storage.
- Alert clips capture temporal context (pre/post event) that a single JPEG cannot.

---

## 2. Plane 1: Metadata JSON → Pulsar

### 2.1 Status: IMPLEMENTED

### 2.2 Flow

```
VideoFileReader ──frame──→ YOLO model.track(persist=True) ──detections──→ PulsarEmitter.emit_frame()
```

### 2.3 Schema — DetectionFrameEvent

```json
{
  "schema_version": "1.0",
  "pipeline_run_id": "a1b2c3d4e5f6",
  "source": {
    "store_id": "store_001",
    "camera_id": "cam_01",
    "stream_id": "cam_01_stream"
  },
  "frame_index": 1502,
  "capture_ts": "2026-05-10T10:30:00.123456+00:00",
  "image_size": {"width": 1920, "height": 1080},
  "detections": [
    {
      "det_id": "1502-0",
      "class": "person",
      "class_id": 0,
      "conf": 0.87,
      "bbox": {"x1": 100.0, "y1": 200.0, "x2": 300.0, "y2": 620.0},
      "bbox_norm": {"x": 0.052, "y": 0.185, "w": 0.104, "h": 0.389},
      "centroid": {"x": 200, "y": 410},
      "centroid_norm": {"x": 0.104, "y": 0.380},
      "track_id": 41
    }
  ],
  "runtime": {
    "model_name": "yolo11n.pt",
    "tracker_type": "botsort"
  }
}
```

Key fields:

| Field | Type | Description |
|-------|------|-------------|
| `pipeline_run_id` | string | Unique per worker restart. Ties frames to a continuous run. |
| `frame_index` | int | Monotonic counter within a pipeline run. |
| `capture_ts` | ISO8601 | UTC timestamp when frame was captured from the reader queue. |
| `detections[].track_id` | int\|null | BoTSORT track ID. `null` if tracker hasn't confirmed the track yet (`n_init` phase). |
| `detections[].bbox_norm` | object | Bbox normalized to [0.0, 1.0] — resolution-independent. |

> `DetectionFrameEvent` nên đứng độc lập với media upload. Nếu một frame được sample và upload thành công, hệ thống có thể phát sinh thêm một `SampledFrameCreatedEvent` để liên kết metadata với object S3, thay vì bắt detection event phải mang theo `s3_frame_key`.

### 2.4 Code path

```
worker.py:91-145
  └── while _reader._running:
        frame = _reader.queue.get(timeout=1.0)
        results = tracker.model.track(source=frame, persist=True, ...)
        detections = [build_detection_dict(obj) for obj in tracker._extract_objects(r)]
        _emitter.emit_frame(...)

emit/pulsar_emitter.py:100-172
  └── emit_frame():
        record = {schema_version, pipeline_run_id, source, ...}
        payload = json.dumps(record).encode('utf-8')
        _send_with_retry(payload, frame_index)
          └── for attempt in range(3):
                producer.send(payload)          # synchronous send
                sleep(0.5 * 2^attempt) on fail  # exponential backoff
```

### 2.5 Retry policy

| Parameter | Value |
|-----------|-------|
| Max retries | 3 |
| Initial backoff | 0.5s |
| Backoff multiplier | 2× |
| Behavior on exhaustion | Log error, drop message, pipeline continues |

> Pulsar producer is synchronous (`producer.send()`). For production, switch to `send_async()` with a callback so the pipeline thread is never blocked by Pulsar latency. Detection publish should remain on the critical path; media upload must not block it.

---

## 3. Plane 2: Sampled JPEG → S3

### 3.1 Status: IMPLEMENTED

### 3.2 Why sample instead of uploading every frame?

```
Full-rate upload (25 fps):
  25 frames/s × 150 KB × 3600 s × 12 h = 162 GB/day/camera
  2 cameras × 162 GB = 324 GB/day → 9.7 TB/month

1-fps sampling:
  1 frame/s × 150 KB × 3600 s × 12 h = 6.48 GB/day/camera
  2 cameras × 6.48 GB = 12.96 GB/day → 389 GB/month

Savings: 25× reduction without losing investigation capability.
```

A 1-second interval is usually sufficient to verify whether a detection was correct in a store aisle, while keeping storage and network cost bounded.

### 3.3 FrameSampler design

```python
# services/vision/emit/frame_sampler.py

import cv2
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class FrameSampler:
    """Upload sampled JPEG frames to S3 asynchronously.

    Sampling strategy:
      - 1 frame per `interval_sec` seconds per camera
      - Sampling decision should be timestamp-based for RTSP
      - Upload via ThreadPoolExecutor (non-blocking, best-effort)
      - S3 key: frames/{event_date}/{store_id}/{camera_id}/{hour}/{timestamp}_{frame_index:09d}.jpg
    """

    def __init__(
        self,
        s3_client,          # boto3.client("s3") or s3 client
        bucket: str,        # "retail-video-analytics"
        store_id: str,
        camera_id: str,
        interval_sec: int = 1,
        jpeg_quality: int = 85,
        max_workers: int = 2,
    ):
        self.s3 = s3_client
        self.bucket = bucket
        self.store_id = store_id
        self.camera_id = camera_id
        self.interval_sec = interval_sec
        self.jpeg_quality = jpeg_quality
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._futures: list = []
        self._last_sample_ts: Optional[datetime] = None
        self._inflight_limit = max_workers * 4

        # Metrics
        self.total_uploaded = 0
        self.total_failed = 0

    def maybe_save(
        self,
        frame,              # BGR numpy array
        frame_index: int,
        fps: float,
        capture_ts: Optional[datetime] = None,
    ) -> Optional[str]:
        """Upload frame to S3 if the sampling interval elapsed.

        Returns the S3 key if uploaded, None otherwise.
        """
        ts = capture_ts or datetime.now(timezone.utc)
        if self._last_sample_ts is not None:
            elapsed = (ts - self._last_sample_ts).total_seconds()
            if elapsed < self.interval_sec:
                return None

        if len([f for f in self._futures if not f.done()]) >= self._inflight_limit:
            logger.warning("Skipping sampled frame %d due to upload backlog", frame_index)
            return None

        key = self._build_key(ts, frame_index)

        # Encode JPEG in memory (avoid disk I/O)
        ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        if not ok:
            logger.warning("JPEG encode failed for frame %d", frame_index)
            return None

        # Upload async — don't block the inference pipeline
        future = self._executor.submit(self._upload, key, buf.tobytes())
        self._futures.append(future)
        self._last_sample_ts = ts

        # Periodic cleanup of completed futures (every 100 frames)
        if len(self._futures) > 100:
            self._futures = [f for f in self._futures if not f.done()]

        return key

    def _build_key(self, ts: datetime, frame_index: int) -> str:
        return (
            f"frames/"
            f"{ts:%Y-%m-%d}/"
            f"{self.store_id}/"
            f"{self.camera_id}/"
            f"{ts:%H}h/"
            f"{ts:%H%M%S}_{frame_index:09d}.jpg"
        )

    def _upload(self, key: str, body: bytes) -> None:
        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=body,
                ContentType="image/jpeg",
            )
            self.total_uploaded += 1
        except Exception:
            self.total_failed += 1
            logger.exception("S3 upload failed: %s", key)

    @property
    def last_sample_ts(self) -> Optional[datetime]:
        return self._last_sample_ts

    def shutdown(self, timeout_sec: float = 10.0) -> None:
        """Wait for pending uploads, then shut down executor."""
        self._executor.shutdown(wait=True, timeout=timeout_sec)
        logger.info(
            "FrameSampler shutdown: uploaded=%d failed=%d",
            self.total_uploaded, self.total_failed,
        )
```

### 3.4 S3 key structure

```
s3://retail-video-analytics/frames/
  {event_date}/              # 2026-05-10     ← partition by date
    {store_id}/              # store_001      ← partition by store
      {camera_id}/           # cam_01         ← partition by camera
        {hour}h/             # 10h            ← hour bucket (avoids flat directory)
          {HHMMSS}_{frame_index:09d}.jpg
                             # 103000_000001502.jpg
```

Example full path:
```
s3://retail-video-analytics/frames/2026-05-10/store_001/cam_01/10h/103000_000001502.jpg
```

Design decisions:

- **`{event_date}` first** — enables date-range prefix deletes for lifecycle policies.
- **`{hour}h/` subfolder** — prevents a single directory from accumulating 86,400 files/day (1fps × 24h).
- **`{frame_index:09d}`** — zero-padded to 9 digits, sortable. Supports up to 999,999,999 frames.
- **Timestamp in filename** — human-readable for ad-hoc inspection without decoding.

### 3.5 Lifecycle policy (production S3)

```json
{
  "Rules": [
    {
      "Id": "expire-sampled-frames",
      "Status": "Enabled",
      "Filter": {"Prefix": "frames/"},
      "Expiration": {"Days": 90}
    }
  ]
}
```

Sampled frames are evidentiary, not archival. 90-day retention balances storage cost with investigation needs.

---

## 4. Plane 3: Alert Clip → S3

### 4.1 Status: IMPLEMENTED (optional, disabled by default)

### 4.2 When to trigger a clip

An alert clip captures **N seconds before + M seconds after** a trigger event. Trigger conditions:

| Trigger | Condition | Rationale |
|---------|-----------|-----------|
| High density | `len(detections) > threshold` (e.g., > 10 people in frame) | Crowd anomaly |
| Track lost | `track.status == "lost"` after being active > 30s | Person disappeared |
| Zone entry | Centroid enters a defined ROI polygon | Restricted area |
| Manual | API call from dashboard | Operator investigation |

### 4.3 AlertClipExtractor design

```python
# services/vision/emit/clip_extractor.py

class AlertClipExtractor:
    """Buffer N seconds of frames, write MP4 clip on trigger.

    Uses a ring buffer of encoded frames to minimize memory.
    """

    def __init__(
        self,
        s3_client,
        bucket: str,
        store_id: str,
        camera_id: str,
        pre_buffer_sec: int = 5,      # seconds before trigger
        post_buffer_sec: int = 5,     # seconds after trigger
        fps: int = 25,
    ):
        self.s3 = s3_client
        self.bucket = bucket
        self.store_id = store_id
        self.camera_id = camera_id
        self.pre_buffer = pre_buffer_sec
        self.post_buffer = post_buffer_sec
        self.fps = fps

        # Ring buffer: encode-on-insert to keep memory bounded.
        # This is acceptable for thesis/demo scope. In production, a rolling
        # encoded segment buffer or a GStreamer/FFmpeg tee is usually better.
        buf_size = pre_buffer_sec * fps
        self._ring: list[bytes | None] = [None] * buf_size
        self._ring_pos = 0

        self._recording = False
        self._post_frames: list[bytes] = []
        self._post_remaining = 0

    def feed(self, frame, frame_index: int) -> None:
        """Feed every frame into the ring buffer (low overhead)."""
        ok, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ok:
            self._ring[self._ring_pos % len(self._ring)] = buf.tobytes()
            self._ring_pos += 1

        if self._recording:
            self._post_frames.append(buf.tobytes() if ok else None)
            self._post_remaining -= 1
            if self._post_remaining <= 0:
                self._finalize_clip()

    def trigger(self, alert_type: str, trigger_frame_index: int) -> str:
        """Start post-buffer recording. Returns alert_id."""
        self._alert_id = f"{self.camera_id}_{trigger_frame_index}_{alert_type}"
        self._recording = True
        self._post_remaining = self.post_buffer * self.fps
        self._trigger_frame = trigger_frame_index
        return self._alert_id

    def _finalize_clip(self) -> None:
        """Encode pre-buffer + post-frames into MP4, upload to S3."""
        # Combine ring buffer (pre) + post_frames
        # Write via cv2.VideoWriter_fourcc to temp file
        # Upload to s3://{bucket}/clips/{date}/{store}/{camera}/{alert_id}.mp4
        # Emit ClipCreatedEvent to Pulsar
        self._recording = False
        self._post_frames.clear()
```

### 4.4 S3 key for clips

```
s3://retail-video-analytics/clips/
  {event_date}/
    {store_id}/
      {camera_id}/
        {alert_id}.mp4
```

Example:
```
s3://retail-video-analytics/clips/2026-05-10/store_001/cam_01/cam_01_1502_density_high.mp4
```

### 4.5 Clip metadata event (Pulsar)

```json
{
  "schema_version": "1.0",
  "event_type": "clip_created",
  "alert_id": "cam_01_1502_density_high",
  "alert_type": "density_high",
  "trigger_frame_index": 1502,
  "clip_s3_key": "clips/2026-05-10/store_001/cam_01/cam_01_1502_density_high.mp4",
  "clip_duration_sec": 10.0,
  "trigger_ts": "2026-05-10T10:30:00.123456+00:00",
  "source": {
    "store_id": "store_001",
    "camera_id": "cam_01"
  }
}
```

---

## 5. Pipeline Integration

### 5.1 Full worker loop (with all 3 planes)

```python
# services/vision/worker.py — current integration

def run_worker(camera_cfg, global_cfg):
    # ... model + tracker + Pulsar setup (unchanged) ...

    # Init FrameSampler when media_upload_enabled=true
    _sampler = FrameSampler(
        s3_client=boto3.client("s3", endpoint_url=global_cfg.get("s3_endpoint")),
        bucket=global_cfg["s3_bucket"],
        store_id=store_id,
        camera_id=camera_id,
        interval_sec=1,
    )

    # Init AlertClipExtractor when alert_clip_enabled=true
    _clip_extractor = AlertClipExtractor(
        s3_client=...,
        bucket=...,
        store_id=store_id,
        camera_id=camera_id,
    )

    # Pipeline loop
    while _reader._running:
        frame = _reader.queue.get(timeout=1.0)
        frame_index += 1

        # --- Inference (blocking, GPU-bound) ---
        results = tracker.model.track(source=frame, persist=True, ...)
        detections = [build_detection_dict(obj) for obj in ...]

        # --- Plane 1: Metadata (must not wait for media upload) ---
        _emitter.emit_frame(
            ...,
        )

        # --- Plane 2: Sampled frame (async upload, non-blocking) ---
        sampled_key = _sampler.maybe_save(frame, frame_index, fps, capture_ts)
        if sampled_key:
            # optional: publish a separate SampledFrameCreatedEvent for correlation
            pass

        # --- Plane 3: Alert clip (ring buffer feed, non-blocking) ---
        _clip_extractor.feed(frame, frame_index)

        # --- Alert trigger check ---
        if len(detections) > ALERT_THRESHOLD:
            alert_id = _clip_extractor.trigger("density_high", frame_index)
```

### 5.2 Thread model

```
┌────────────────────────────────────────────────────────────┐
│ Worker Process (pid=1001)                                   │
│                                                             │
│  Main thread (inference loop):                              │
│    frame = queue.get()                                      │
│    results = model.track(frame)         ← GPU, ~30ms        │
│    detections = build_list(results)     ← CPU, ~1ms         │
│    emitter.emit_frame(detections)       ← sync, ~2ms        │
│    sampler.maybe_save(frame)            ← non-blocking      │
│    clip_extractor.feed(frame)           ← non-blocking      │
│                                                             │
│  Reader thread (daemon):                                    │
│    cap.read() → queue.put(frame)        ← I/O bound         │
│                                                             │
│  Upload threads (ThreadPoolExecutor, max=2):                │
│    s3.put_object(key, jpeg_bytes)       ← I/O bound         │
│                                                             │
│  Total: 1 inference + 1 reader + 2 upload = 4 threads       │
│  Only inference thread touches GPU. Thread-safe via queue.  │
└────────────────────────────────────────────────────────────┘
```

### 5.3 Timing budget (per frame at 25fps = 40ms budget)

| Step | Thread | Time (ms) | Cumulative |
|------|--------|-----------|------------|
| `queue.get()` | Main | 0-40 | — (blocking, depends on reader) |
| `model.track()` | Main | 25-35 | 35 ms |
| `build_detections()` | Main | 1-2 | 37 ms |
| `emitter.emit_frame()` | Main | 1-3 | 40 ms |
| `sampler.maybe_save()` | Main → Upload | 0.1 (submit) | 40.1 ms |
| `clip_extractor.feed()` | Main | 0.5 | 40.6 ms |

> The main thread stays within the 40ms budget. Upload I/O happens on background threads and does not block the next frame inference.

---

## 6. Production notes

### 6.1 What should stay on the hot path?

- Frame read
- Detection and tracking
- Detection event publish to Pulsar

### 6.2 What should stay off the hot path?

- JPEG upload to S3
- Clip assembly and upload
- Any object-storage retry loop

### 6.3 Production optimization

Production systems usually do one of the following:

- Store sampled frames only, not every frame.
- Keep a short rolling raw/encoded buffer and cut clips from that buffer.
- Upload media asynchronously from a separate media worker or sidecar.
- Use lifecycle policies aggressively so object storage does not grow without bound.

For this thesis, the current design is valid if the upload path is best-effort and never blocks inference.

## 7. Configuration

### 7.1 `cameras.yaml` additions

```yaml
# configs/cameras.yaml — additions for data extraction

settings:
  # --- Existing (unchanged) ---
  model_name: yolo11n.pt
  tracker_type: botsort
  # ...

  # --- Plane 1: Pulsar ---
  pulsar_service_url: pulsar://localhost:6650
  pulsar_topic: persistent://retail/metadata/events

  # --- Plane 2: Frame sampling ---
  s3_endpoint: https://s3.ap-southeast-2.amazonaws.com          # AWS S3 local; https://s3.ap-southeast-1.amazonaws.com for prod
  s3_bucket: retail-video-analytics
  s3_access_key: CHANGE_ME
  s3_secret_key: CHANGE_ME
  s3_region: ap-southeast-1
  frame_sample_interval_sec: 1                # 1 JPEG per second per camera
  frame_jpeg_quality: 85                      # 0-100, 85 balances size/quality

  # --- Plane 3: Alert clips ---
  alert_density_threshold: 10                 # >10 people in frame → alert
  alert_pre_buffer_sec: 5
  alert_post_buffer_sec: 5
```

### 7.2 Environment variable overrides

```bash
# .env overrides (highest priority)
S3_ENDPOINT=https://s3.ap-southeast-2.amazonaws.com
S3_BUCKET=retail-video-analytics
FRAME_SAMPLE_INTERVAL_SEC=1
```

---

## 7. Downstream consumption

### 7.1 How Flink reads this data

```
Pulsar source (JSON metadata)
  │
  ├── Bronze: raw ingest → Iceberg bronze_detection_frames
  │     SELECT *, event_date FROM pulsar_source
  │
  ├── Silver: flatten detections and keep media correlation keys optional
  │     SELECT explode(detections) AS det, frame_index, capture_ts, ...
  │     FROM bronze_detection_frames
  │
  └── Gold: aggregate metrics (count per minute, heatmap)
        SELECT camera_id, window_start, count(*), ...
        FROM silver_detections
        GROUP BY camera_id, TUMBLE(1 MINUTE)
```

### 7.2 How dashboard renders a frame

```
1. User opens dashboard → API call: GET /api/cameras/cam_01/frames?ts=2026-05-10T10:30:00
2. FastAPI queries Trino:
     SELECT event_id, capture_ts, detections
     FROM lakehouse.retail.silver_detections
     WHERE camera_id = 'cam_01'
       AND capture_ts BETWEEN '2026-05-10T10:29:55' AND '2026-05-10T10:30:05'
     ORDER BY capture_ts DESC
     LIMIT 1
3. FastAPI resolves the matching sampled-frame reference from the media index or side event stream
4. FastAPI generates pre-signed S3 URL for the frame object (5-min expiry)
5. Frontend renders: <img src={presigned_url} /> + bounding box overlay from detections JSON
```

### 7.3 How dashboard plays a clip

```
1. Alert list in dashboard → click "View Clip"
2. API: GET /api/clips/cam_01_1502_density_high/playback
3. FastAPI queries Iceberg for clip_s3_key
4. Returns pre-signed URL → <video src={presigned_url} controls />
```

---

## 8. Storage estimation (2 cameras, 12h/day operation)

| Data type | Rate | Size/unit | Daily | Monthly | Yearly |
|-----------|------|-----------|-------|---------|--------|
| JSON metadata | 25 fps × 2 cams × 12h/day | 2 KB | 4.3 GB | 129 GB | 1.6 TB |
| Sampled JPEG | 1 fps × 2 cams × 12h/day | 150 KB | 13.0 GB | 389 GB | 4.7 TB |
| Alert clips (est.) | 10 alerts/day | 5 MB | 50 MB | 1.5 GB | 18 GB |
| **Total** | | | **17.3 GB** | **519 GB** | **6.3 TB** |

Iceberg compaction + Parquet compression reduces metadata by ~3× at rest.

---

## 9. Implementation status

| Component | Status | Notes |
|-----------|--------|-------|
| `FrameSampler` | Implemented | Upload sampled JPEGs asynchronously to S3. |
| `SampledFrameCreatedEvent` | Implemented | Published to `persistent://retail/metadata/media-events` after successful upload. |
| `AlertClipExtractor` | Implemented, disabled by default | Enable with `alert_clip_enabled: true`. |
| `ClipCreatedEvent` | Implemented | Published after MP4 upload succeeds. |
| AWS S3 bucket setup | Implemented | Uses existing local `warehouse` bucket. |
| FastAPI pre-signed URL endpoint | Not implemented | Future serving-layer work. |

---

## 10. Key design decisions summary

| Decision | Rationale |
|----------|-----------|
| JSON goes to Pulsar, NOT S3 | Pulsar is for streaming events; S3 is for binary objects. Flink reads Pulsar natively. |
| 1fps sampling, not 25fps | 25× storage savings. 1 second granularity is sufficient for person tracking verification. |
| Upload async via ThreadPoolExecutor | Inference thread must not block on S3 I/O (40ms budget). |
| Ring buffer for clip pre-buffer | Encode-on-insert keeps memory bounded at `pre_buffer_sec × fps` frames. |
| Separate media event for sampled frames | Keeps detection events pure and avoids coupling inference latency to object storage writes. |
| Timestamp in S3 key filename | Human-readable without a metadata lookup. Sortable for sequential access. |
| 90-day frame lifecycle | Evidentiary data, not archival. Reduces long-term storage cost. |
