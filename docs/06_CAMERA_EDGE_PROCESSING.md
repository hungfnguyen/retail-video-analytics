# Camera Edge Processing

## Responsibility

The Vision service is the edge processing layer. It converts camera/video frames into metadata and live media artifacts.

## Inputs

- Camera definitions from `configs/cameras.yaml`.
- Video files or camera streams.
- YOLO model configuration.
- Tracker configuration.

## Outputs

| Output | Destination | Purpose |
|---|---|---|
| Detection frame event | Pulsar `persistent://retail/metadata/events` | Stream processing input |
| Latest annotated JPEG | `runtime/live_frames/{camera_id}.jpg` | Live dashboard media |
| Live frame metadata | `runtime/live_frames/{camera_id}.json` | Media FPS/latency/count stats |
| Sampled JPEG | AWS S3 `frames/` | Investigation/replay sample |
| Optional alert clip | AWS S3 `clips/` | Incident artifact |

## Processing Loop

```text
VideoFileReader -> tracking_safe queue -> YOLO predict -> sv.Detections
  -> Roboflow ByteTrack -> smoothing -> TrackMemory global_track_id
  -> bottom-center anchors -> PolygonZone / LineZone facts
  |-- publish Pulsar event
  |-- write latest annotated JPEG
  |-- optional sampled media upload
```

The default `tracking_safe` frame policy keeps a short queue so tracker state sees a more continuous sequence while still dropping under sustained backlog.

## Current Model Settings

Configured in `configs/cameras.yaml`:

```yaml
model_name: yolo11l.pt
detector_type: ultralytics_yolo
tracker_type: roboflow_bytetrack
conf_thres: 0.15
class_filter: [0]
frame_policy:
  mode: tracking_safe
  max_queue_size: 4
publish_vision_facts: true
zones_config_path: configs/zones.yaml
live_media_fps: 15
live_media_jpeg_quality: 75
```

`class_filter: [0]` means the current pipeline focuses on person detection.

## GPU/CPU

The Vision worker uses the detector device selected by Ultralytics and then runs Roboflow Trackers over `sv.Detections`. On machines with CUDA correctly installed, the model can run on GPU. On CPU, the pipeline still runs but with lower FPS.

## Failure Handling

| Failure | Behavior |
|---|---|
| Video read hiccup | Reader continues or reconnects according to source behavior |
| Queue overload | Oldest frame is dropped |
| Pulsar publish failure | Producer retry logic applies |
| S3 media upload backlog | Sampled frame upload can be skipped |
| Live media write failure | Logged; metadata stream can continue |
