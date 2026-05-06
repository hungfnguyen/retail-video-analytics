# Camera Edge Processing

## 1. Mục tiêu

Camera edge processing là entry point của hệ thống. Module này chuyển video thành detection metadata có schema rõ ràng. Nó phải chạy ổn định, không để camera lỗi làm sập toàn bộ pipeline và không để I/O chặn inference loop.

## 2. Input và output

### Input

- RTSP camera stream.
- Video file dùng cho demo.
- Camera config từ `cameras.yaml` hoặc PostgreSQL.

### Output

| Output | Đích | Tần suất |
|---|---|---:|
| DetectionFrameEvent | Pulsar | Mỗi frame xử lý |
| Sampled frame JPEG | GCS | 1 frame/giây hoặc cấu hình |
| Track lifecycle | PostgreSQL hoặc Pulsar | start/sample/end |
| Camera/system metrics | Prometheus hoặc Pulsar | 5 đến 10 giây |

## 3. Component architecture

```text
CameraManager
    |
    +--> CameraWorker(cam_01)
    |       |
    |       +--> RTSPReader thread
    |       +--> YOLO Detector
    |       +--> BoTSORT Tracker
    |       +--> DetectionPublisher
    |       +--> FrameSampler
    |
    +--> CameraWorker(cam_02)
    |
    +--> Health check loop
```

## 4. CameraManager

CameraManager là process chính của vision service.

Trách nhiệm:

- Load camera config.
- Spawn một worker cho mỗi camera enabled.
- Theo dõi worker health.
- Restart worker khi crash.
- Handle SIGTERM/SIGINT để shutdown sạch.
- Emit camera health metrics.

Pseudo behavior:

```text
start_all()
while running:
    for each worker:
        if worker is dead:
            restart worker
    sleep(health_check_interval)
stop_all() on SIGTERM
```

## 5. CameraWorker

Mỗi camera chạy trong một OS process riêng.

Lý do:

- Tránh Python GIL giữa nhiều camera.
- Crash một camera không ảnh hưởng camera khác.
- Tracker state riêng theo camera.
- Có thể restart độc lập.

Worker pipeline:

```text
get latest frame
    |
    v
YOLO inference
    |
    v
BoTSORT tracking
    |
    v
build DetectionFrameEvent
    |
    +--> publish Pulsar
    +--> upload sampled frame
    +--> update track lifecycle
```

## 6. RTSPReader

RTSPReader chạy thread riêng trong worker.

Yêu cầu:

- Dùng `cv2.VideoCapture` hoặc backend FFmpeg.
- Set buffer nhỏ nếu backend hỗ trợ.
- Queue size 1 đến 2 frame.
- Khi queue đầy, drop frame cũ để lấy frame mới nhất.
- Có reconnect logic với exponential backoff.

Reconnect policy:

| Attempt | Delay |
|---:|---:|
| 1 | 1 giây |
| 2 | 2 giây |
| 3 | 4 giây |
| N | min(2^(N-1), 30 giây) |

## 7. Frame dropping strategy

Đối với realtime analytics, frame mới quan trọng hơn xử lý đủ mọi frame.

Quy tắc:

- Không để OpenCV buffer tích lũy nhiều frame.
- Nếu inference chậm, bỏ frame cũ trong queue.
- `frame_index` vẫn tăng theo frame đọc được hoặc theo frame xử lý, cần định nghĩa rõ trong event contract.

Đề xuất:

- `source_frame_index`: frame đọc từ stream nếu biết.
- `processed_frame_index`: số frame thực sự qua model.
- MVP có thể chỉ dùng `frame_index = processed_frame_index`.

## 8. Detector và tracker

### Detector

| Setting | Giá trị đề xuất |
|---|---|
| Model | YOLO11n hoặc YOLO11s |
| Class filter | person |
| Confidence threshold | 0.4 hoặc 0.5 |
| Device | `cuda:0` nếu có GPU, `cpu` cho demo nhỏ |
| Input size | 640 hoặc theo benchmark |

### Tracker

| Setting | Giá trị |
|---|---|
| Tracker | BoTSORT |
| Scope | Một camera |
| Track timeout | 30 giây |
| Output | `track_id`, bbox, centroid |

Lưu ý: `track_id` không phải định danh con người thật và không nên dùng để nhận diện cá nhân.

## 9. DetectionPublisher

Publisher không được block inference loop quá lâu.

| Sink | Cách gửi |
|---|---|
| Pulsar | Async producer, batching nhỏ |
| GCS | ThreadPoolExecutor hoặc async upload queue |
| PostgreSQL | Async pool, sample position theo interval |
| Metrics | Non-blocking best-effort |

Nếu Pulsar tạm unavailable:

- Retry với backoff.
- Buffer giới hạn N events trong memory.
- Nếu buffer đầy, drop realtime events và tăng metric.
- Không làm worker treo vô hạn.

## 10. Sampled frame strategy

Không lưu mọi frame.

| Setting | Giá trị |
|---|---:|
| Save interval | 1 giây |
| JPEG quality | 80 đến 85 |
| Path includes | date, store_id, camera_id, hour, frame_index |
| Retention | 7 ngày cho demo |

Sampled frame được dùng để:

- Hiển thị frame tại thời điểm alert.
- Minh họa track replay.
- Debug model.

Không dùng sampled frame làm source chính cho analytics.

## 11. Track lifecycle

Track lifecycle manager giữ state local theo camera.

Events:

- `track_start`: track_id xuất hiện lần đầu.
- `position_sample`: ghi mỗi 1 giây khi track còn active.
- `track_end`: track mất tín hiệu quá timeout.

State key:

```text
(camera_id, track_id)
```

Timeout:

```text
if now - last_seen > 30 seconds:
    emit track_end
```

## 12. Camera configuration

`configs/cameras.yaml`:

```yaml
cameras:
  - camera_id: cam_01
    store_id: store_001
    name: Entrance
    source_type: video_file
    source_uri: data/videos/sample.mp4
    enabled: true
    fps_target: 25
    resolution_width: 1920
    resolution_height: 1080

settings:
  health_check_interval_sec: 10
  frame_queue_size: 2
  reconnect_delay_initial_sec: 1
  reconnect_delay_max_sec: 30
  frame_save_interval_sec: 1
```

## 13. Environment variables

```env
VISION_MODEL_PATH=data/models/yolo11n.pt
VISION_DEVICE=cuda:0
VISION_CONFIDENCE_THRESHOLD=0.4
VISION_TRACKER=botsort

PULSAR_SERVICE_URL=pulsar://pulsar:6650
PULSAR_TOPIC_DETECTION_FRAMES=persistent://rva/ingest/detection-frames-v1

POSTGRES_DSN=postgresql://rva:rva_secret@postgres:5432/rva_metadata
REDIS_URL=redis://redis:6379

GCS_BUCKET_NAME=rva-frames
GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcs-service-account.json
```

## 14. Failure scenarios

| Scenario | Expected behavior |
|---|---|
| Camera disconnect | RTSPReader reconnects |
| Worker crash | CameraManager restarts worker |
| GPU OOM | Worker logs error, exits, manager restarts after backoff |
| Pulsar unavailable | Publisher retries and buffers bounded events |
| GCS upload fail | Skip frame after retry, metadata still published |
| PostgreSQL fail | Track lifecycle retry or degrade temporarily |
| Redis fail | Vision path continues because Redis is not direct dependency |

## 15. Resource estimate for demo

| Scale | CPU | RAM | GPU |
|---|---:|---:|---|
| 1 video/camera | 2 đến 4 cores | 4 đến 8 GB | Optional, T4 tốt hơn |
| 2 đến 4 cameras | 8 cores | 16 đến 30 GB | NVIDIA T4 |
| 4 đến 8 cameras | 16 cores | 30 đến 60 GB | T4/A10 tùy model |

## 16. Unit tests

- RTSPReader reconnect khi `read()` fail.
- Queue drop stale frame khi full.
- Detection event build đúng schema.
- FrameSampler chỉ save theo interval.
- TrackLifecycleManager sinh start/sample/end đúng.
- Publisher retry khi sink lỗi.
- CameraManager restart worker dead.

## 17. Success criteria

- Chạy được một video file và publish detection events vào Pulsar.
- CameraWorker không block khi GCS upload chậm.
- Worker crash được CameraManager restart.
- Event có `event_id`, `camera_id`, `capture_ts`, `detections`.
- Sampled frame path được gắn vào event khi có frame được lưu.

