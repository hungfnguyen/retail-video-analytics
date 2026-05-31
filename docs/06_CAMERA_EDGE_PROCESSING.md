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
VideoFileReader -> queue(size=1) -> YOLO track -> normalize detections
                                      |-- publish Pulsar event
                                      |-- write latest annotated JPEG
                                      |-- optional sampled media upload
```

The queue intentionally drops old frames under pressure. For realtime video analytics, a fresh frame is more valuable than preserving every frame in the edge buffer.

## Current Model Settings

Configured in `configs/cameras.yaml`:

```yaml
model_name: yolo11l.pt
tracker_type: botsort
conf_thres: 0.25
class_filter: [0]
frame_queue_size: 1
live_media_fps: 15
live_media_jpeg_quality: 75
```

`class_filter: [0]` means the current pipeline focuses on person detection.

## GPU/CPU

The Vision worker uses the tracker/model device selected by Ultralytics and project configuration. On machines with CUDA correctly installed, the model can run on GPU. On CPU, the pipeline still runs but with lower FPS.

## Failure Handling

| Failure | Behavior |
|---|---|
| Video read hiccup | Reader continues or reconnects according to source behavior |
| Queue overload | Oldest frame is dropped |
| Pulsar publish failure | Producer retry logic applies |
| S3 media upload backlog | Sampled frame upload can be skipped |
| Live media write failure | Logged; metadata stream can continue |
