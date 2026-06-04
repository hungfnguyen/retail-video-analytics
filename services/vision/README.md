# Retail Vision Service

`services/vision` is the edge feature extraction service for Retail Video Analytics.
The current runtime is fully based on Supervision-compatible detections and
Roboflow Trackers:

```text
video frame
  -> Ultralytics YOLO predict
  -> sv.Detections
  -> Roboflow ByteTrackTracker
  -> DetectionsSmoother
  -> TrackMemory global_track_id stabilizer
  -> bottom-center anchors
  -> PolygonZone / LineZone facts
  -> Pulsar metadata events + annotated live media
```

The previous tracker-specific prototype stack and standalone `main2.py`
experiment have been removed. Do not add new code against those APIs; add
adapters around Supervision or Roboflow Trackers instead.

## Main Files

```text
services/vision/
├── main.py
├── worker.py
├── reader.py
├── config/settings.py
├── detect/supervision_yolo_detector.py
├── track/roboflow_tracker.py
├── track/track_memory.py
├── features/detections.py
├── zones/zone_manager.py
├── emit/pulsar_emitter.py
└── media/live_frame_publisher.py
```

## Configuration

Production uses `configs/cameras.yaml` and `configs/zones.yaml`. The important
Vision defaults are:

```yaml
settings:
  model_name: yolo11l.pt
  detector_type: ultralytics_yolo
  conf_thres: 0.15
  class_filter: [0]
  tracker_type: roboflow_bytetrack
  frame_policy:
    mode: tracking_safe
    max_queue_size: 4
  publish_vision_facts: true
  zones_config_path: configs/zones.yaml
```

Use `services/vision/.env` only for single-camera fallback or local overrides.
For production overrides prefer `RVA_MODEL_NAME`, `RVA_TRACKER_TYPE`,
`RVA_CONF_THRES`, and `RVA_CLASS_FILTER` so an old `.env` does not silently
override YAML.

## Zone Calibration

1. Extract a representative frame for each camera.
2. Draw polygons/lines in https://polygonzone.roboflow.com/.
3. Store normalized points in `configs/zones.yaml`.
4. Restart Vision so `RetailZoneRuntime` loads the new zone version.

`PolygonZone` membership uses bottom-center anchors by default because this is
closest to a person's foot position on the shop floor.

## Running

From the repository root:

```bash
uv run --package rva-vision python services/vision/main.py
```

Expected startup logs include:

```text
Loading rebuilt Vision pipeline
YOLO detector ready
Rebuilt Vision pipeline loaded successfully: effective_tracker=roboflow_bytetrack
Loaded zone config ...
Pipeline loop starting: frame_policy=tracking_safe
```

## Output

Vision publishes frame events to `persistent://retail/metadata/events` and media
events to `persistent://retail/metadata/media-events` when media upload is
enabled. Each detection event can include:

- `frame_metrics` for FPS, dropped frames, inference/tracking/zone timing
- raw `track_id` from Roboflow Trackers
- stable `global_track_id` from TrackMemory
- bottom-center `anchor`
- `zones` and frame-level `zone_counts`
- `line_crossings`
- annotated live frame files under `runtime/live_frames`

Realtime Flink consumes these events for Redis live keys; lakehouse jobs keep
legacy silver/gold tables and add v2 tables for Supervision/global-id fields.
