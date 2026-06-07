# Data Flow And Contracts

## Topics

| Topic | Purpose |
|---|---|
| `persistent://retail/metadata/events` | Detection frame events from Vision |
| `persistent://retail/metadata/media-events` | Optional sampled frame / clip artifact events |
| `persistent://retail/metadata/dlq-events` | Invalid detection events from realtime validation |

`events` is partitioned by camera count so events for a camera can preserve ordering through a stable partition key.

## Detection Event Contract

Vision publishes JSON events with this shape:

```json
{
  "schema_version": "1.0",
  "event_id": "...",
  "pipeline_run_id": "...",
  "frame_index": 123,
  "capture_ts": "2026-05-28T15:39:58.123Z",
  "source": {
    "store_id": "store_001",
    "camera_id": "cam_01",
    "source_type": "video_file"
  },
  "image_size": {
    "width": 1280,
    "height": 720
  },
  "detections": [
    {
      "det_id": "123-0",
      "class": "person",
      "class_id": 0,
      "conf": 0.86,
      "track_id": 42,
      "raw_track_id": 18,
      "global_track_id": "cam_01_g_000042",
      "bbox": {"x1": 100, "y1": 120, "x2": 220, "y2": 420},
      "bbox_norm": {"x": 0.078, "y": 0.166, "w": 0.093, "h": 0.416},
      "centroid": {"x": 160, "y": 270},
      "centroid_norm": {"x": 0.125, "y": 0.375},
      "anchor": {"type": "bottom_center", "x": 160, "y": 420, "x_norm": 0.125, "y_norm": 0.583},
      "zones": [{"zone_id": "checkout_queue_01", "zone_type": "queue", "is_primary": true}],
      "queue": {"in_queue": true, "queue_zone_id": "checkout_queue_01"}
    }
  ],
  "runtime": {
    "model_name": "yolo11l.pt",
    "detector_type": "ultralytics_yolo",
    "tracker_type": "roboflow_bytetrack",
    "supervision_version": "0.28.0",
    "trackers_version": "2.4.0"
  },
  "zone_counts": [{"zone_id": "checkout_queue_01", "zone_type": "queue", "count": 1}],
  "line_crossings": []
}
```

## Identity Fields

| Field | Meaning |
|---|---|
| `event_id` | Deterministic frame event id, used for deduplication |
| `pipeline_run_id` | Vision process/run identifier |
| `source.camera_id` | Camera scope for ordering and serving |
| `source.store_id` | Store grouping key |
| `frame_index` | Frame number within the Vision run |
| `track_id` | Application-stabilized integer identity scoped to a camera/run |
| `raw_track_id` | Native ID emitted by Roboflow Trackers |
| `global_track_id` | Stable string identity used by realtime/lakehouse business metrics |

## Storage Contracts

### Redis

```text
stats:count:{camera_id}                 current person count, short TTL
live:frame:{camera_id}                  latest parsed frame metadata, short TTL
heatmap:live:{camera_id}                sorted set of grid cells
track:active:{camera_id}:{global_track_id} hash with bbox/grid/last_seen/confidence/zone
alerts:recent:{camera_id}               recent alert JSON list for one camera
alerts:recent:store:{store_id}          recent alert JSON list for one store
alerts:cooldown:{camera_id}:{alert_type} short TTL key to prevent alert spam
```

### Iceberg

```text
lakehouse.rva.bronze_raw
lakehouse.rva.silver_detections          legacy-compatible detection rows
lakehouse.rva.silver_detections_v2       Supervision/global-id/zone detection rows
lakehouse.rva.gold_track_summary         legacy-compatible track summary
lakehouse.rva.gold_track_summary_v2      global_track_id-based track summary
lakehouse.rva.gold_camera_hourly_metrics
lakehouse.rva.gold_camera_daily_metrics
lakehouse.rva.gold_camera_daily_dwell
lakehouse.rva.gold_alert_events
```

`gold_alert_events` stores alert metadata only. Video evidence remains in S3 and
is linked through `clip_s3_uri` when clip extraction is enabled.

### AWS S3 Media

```text
frames/{date}/{store_id}/{camera_id}/{hour}h/{HHMMSS}_{frame_index}.jpg
clips/{date}/{store_id}/{camera_id}/{alert_id}.mp4
```

Media upload is optional and controlled by `media_upload_enabled` in `configs/cameras.yaml`.

## Compatibility Notes

- Raw payload is kept in Bronze so downstream parsing can evolve.
- Silver filters only valid person detections with sufficient confidence.
- Realtime state is TTL based; Iceberg is the analytical source of truth.
- Redis writes are low-latency serving state and should not be treated as historical storage.
