# Vision Multi-Camera Flow

## Current Configuration

Cameras are defined in `configs/cameras.yaml`:

```yaml
cameras:
  - camera_id: cam_01
    store_id: store_001
    source_type: video_file
    source_uri: data/videos/video1.mp4
    enabled: true

  - camera_id: cam_02
    store_id: store_001
    source_type: video_file
    source_uri: data/videos/video2.mp4
    enabled: true
```

## Process Model

```text
services/vision/main.py
  -> load camera config
  -> start one worker process per enabled camera
  -> monitor workers
  -> restart failed worker within configured limit
```

Each worker owns its camera reader, tracker, Pulsar producer, live media publisher, and optional media upload helpers.

## Per-Camera Worker

```text
VideoFileReader
  -> bounded frame queue
  -> YOLO11 track call
  -> DetectionFrameEvent
  -> Pulsar metadata event
  -> annotated latest JPEG
  -> optional sampled frame upload
```

## Output Planes

| Plane | Destination | Notes |
|---|---|---|
| Metadata | Pulsar `persistent://retail/metadata/events` | Main data stream |
| Live media | `runtime/live_frames/{camera_id}.jpg` | Overwritten latest annotated frame |
| Live metadata | `runtime/live_frames/{camera_id}.json` | FPS, latency, count, processing metrics |
| Sampled frames | AWS S3 `frames/` | Optional, configured by `media_upload_enabled` |
| Clips | AWS S3 `clips/` | Optional, disabled by default |

## Realtime Constraints

- Frame queue is small to avoid backlog.
- Old frames are dropped under pressure.
- Video media is not sent through Redis or Flink.
- Detection events keep bbox and normalized coordinates so downstream systems can render or aggregate if needed.

## Operational Notes

- GPU availability should be verified with `torch.cuda.is_available()` in the `rva-vision` environment.
- If Vision runs on CPU, lower `live_media_fps`, model size, or camera count.
- If AWS S3 upload is not needed for a run, set `media_upload_enabled: false` in camera config.
