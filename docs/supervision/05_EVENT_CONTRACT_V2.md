# Event Contract V2

## Goal

Extend the current `DetectionFrameEvent` contract so Vision can emit richer
retail facts while preserving v1 migration safety.

V2 adds:

- source frame and ingest timestamps;
- runtime versions for Supervision and Trackers;
- frame-level processing metrics;
- zone counts;
- line crossings;
- bottom-center anchors;
- global track IDs;
- detection-level zone and queue metadata;
- quality flags.

## Compatibility Rule

V1 fields remain available:

```text
schema_version
event_id
pipeline_run_id
frame_index
capture_ts
source
image_size
detections
runtime
bbox
bbox_norm
centroid
centroid_norm
track_id
```

During migration:

- Bronze stores raw v1 and v2 payloads.
- Flink parsers accept v1 and v2.
- Redis/FastAPI can continue serving v1 fields until v2 keys are implemented.
- New v2 fields are optional for consumers until their jobs are upgraded.

## Frame Event Shape

```json
{
  "schema_version": "2.0",
  "event_type": "detection_frame",
  "event_id": "deterministic-id",
  "pipeline_run_id": "vision-run-id",
  "frame_index": 123,
  "source_frame_index": 456,
  "capture_ts": "2026-06-02T10:15:30.123Z",
  "ingest_ts": "2026-06-02T10:15:30.180Z",
  "source": {
    "store_id": "store_001",
    "camera_id": "cam_01",
    "source_type": "video_file",
    "source_uri_hash": "sha256:..."
  },
  "image_size": {
    "width": 1280,
    "height": 720
  },
  "runtime": {
    "model_name": "yolo11l.pt",
    "detector_type": "ultralytics_yolo",
    "tracker_type": "bytetrack",
    "supervision_version": "x.y.z",
    "trackers_version": "x.y.z",
    "zone_config_version": "zones-2026-06-v1"
  },
  "frame_metrics": {},
  "zone_counts": [],
  "line_crossings": [],
  "detections": []
}
```

## Frame Metrics

```json
{
  "people_count": 5,
  "raw_detection_count": 7,
  "tracked_detection_count": 5,
  "dropped_frames_since_last": 2,
  "source_fps": 25.0,
  "effective_fps": 12.4,
  "decode_ms": 3,
  "inference_ms": 68,
  "tracking_ms": 4,
  "zone_ms": 1,
  "publish_ms": 2,
  "total_ms": 82
}
```

These fields support tracking-quality evaluation and system-health dashboards.

## Zone Counts

```json
{
  "zone_id": "checkout_queue_01",
  "zone_type": "queue",
  "count": 3,
  "track_ids": [12, 18, 21],
  "global_track_ids": [
    "cam_01_g_000012",
    "cam_01_g_000018",
    "cam_01_g_000021"
  ]
}
```

`track_ids` and `global_track_ids` are diagnostic fields. Flink may use them for
stateful live metrics but should still derive sessions from detections.

## Line Crossings

```json
{
  "line_id": "entrance_line_01",
  "line_type": "entrance_exit",
  "direction": "in",
  "track_id": 12,
  "global_track_id": "cam_01_g_000012"
}
```

Directions are defined by `configs/zones.yaml`.

## Detection Object

```json
{
  "det_id": "123-0",
  "class": "person",
  "class_id": 0,
  "conf": 0.86,
  "track_id": 42,
  "global_track_id": "cam_01_g_000042",
  "track_status": "tracked",
  "bbox": {
    "x1": 100,
    "y1": 120,
    "x2": 220,
    "y2": 420
  },
  "bbox_norm": {
    "x": 0.078,
    "y": 0.166,
    "w": 0.093,
    "h": 0.416
  },
  "centroid": {
    "x": 160,
    "y": 270
  },
  "centroid_norm": {
    "x": 0.125,
    "y": 0.375
  },
  "anchor": {
    "type": "bottom_center",
    "x": 160,
    "y": 420,
    "x_norm": 0.125,
    "y_norm": 0.583
  },
  "zones": [
    {
      "zone_id": "checkout_queue_01",
      "zone_name": "Checkout Queue 01",
      "zone_type": "queue",
      "is_primary": true
    }
  ],
  "queue": {
    "in_queue": true,
    "queue_zone_id": "checkout_queue_01"
  },
  "quality": {
    "bbox_area": 30000,
    "is_near_frame_edge": false,
    "is_low_confidence": false,
    "is_zone_boundary_near": false
  }
}
```

## Validation Rules

Required top-level fields:

- `schema_version`;
- `event_type`;
- `event_id`;
- `pipeline_run_id`;
- `frame_index`;
- `capture_ts`;
- `source.store_id`;
- `source.camera_id`;
- `image_size.width`;
- `image_size.height`;
- `detections`.

Required detection fields:

- `det_id`;
- `class`;
- `class_id`;
- `conf`;
- `bbox`;
- `bbox_norm`;
- `centroid`;
- `centroid_norm`.

Optional but recommended v2 fields:

- `track_id`;
- `global_track_id`;
- `anchor`;
- `zones`;
- `queue`;
- `quality`.

Invalid events go to DLQ with reason and raw payload.

