# Vision Service — Edge Processing

## 1. Tổng quan

Vision Service là thành phần xử lý video, chạy trên máy local có GPU. Nó đọc video file, chạy inference YOLO11, tracking ByteTrack, phát hiện zone, rồi publish kết quả sang Pulsar.

**Vị trí code:** `services/vision/`

## 2. Kiến trúc nội bộ

```
main.py (CameraManager)
    │
    ├── SharedYOLOInferenceProcess  ← 1 process duy nhất chạy YOLO trên GPU
    │       model: yolo11l.pt
    │       imgsz: 1280, half: true, iou: 0.70
    │
    ├── WorkerProcess [cam_01]      ← 1 process per camera
    │       │
    │       ├── VideoReader         ← đọc video file theo vòng lặp
    │       ├── FrameQueue          ← buffer frames (tracking_safe mode)
    │       ├── SharedInferenceClient ← gửi frame lên YOLO process, nhận bbox
    │       ├── RoboflowTracker     ← ByteTrack tracking
    │       ├── ZoneManager         ← polygon-based zone assignment
    │       ├── TrackMemory         ← bridge occlusion ngắn (2000ms TTL)
    │       ├── PulsarEmitter       ← publish event JSON → Pulsar
    │       ├── LiveFramePublisher  ← ghi annotated JPEG → Redis
    │       ├── FrameSampler        ← upload sample frames → S3 (optional)
    │       └── ClipExtractor       ← buffer frames, tạo clip khi alert
    │
    └── WorkerProcess [cam_02]      ← tương tự
```

## 3. Shared Inference Pattern

**Vấn đề:** Mỗi camera worker là 1 process riêng. Nếu load YOLO model riêng mỗi process → tốn ~8GB VRAM cho 2 cameras.

**Giải pháp:** 1 process YOLO duy nhất, các workers gửi frame qua `multiprocessing.Queue`:

```
Worker cam_01 ──┐
                ├──▶ SharedYOLOProcess ──▶ YOLO batch inference ──▶ results
Worker cam_02 ──┘         (GPU)
```

**Config (`cameras.yaml`):**
```yaml
shared_inference_enabled: true
shared_inference_queue_size: 8
shared_inference_timeout_sec: 30
```

## 4. Tracking

**Model:** Roboflow Trackers 2.x (ByteTrack)

**Identity fields:**
- `track_id`: integer ổn định, scope trong 1 camera/run session
- `raw_track_id`: native ID từ ByteTrack
- `global_track_id`: string ổn định dùng cho analytics, format: `cam_01_g_000042`

**TrackMemory:** bridge occlusion ngắn (khi người bị che khuất vài frame):
```yaml
track_memory_enabled: true
track_lost_ttl_ms: 2000      # giữ track 2 giây khi lost
track_lost_ttl_frames: 30    # tối đa 30 frame
track_smooth_alpha: 0.65     # exponential smoothing cho bbox
track_predicted_conf_decay: 0.85  # confidence decay khi predict
```

**Config chất lượng:**
```yaml
conf_thres: 0.15             # ngưỡng detection confidence
track_activation_threshold: 0.20
minimum_consecutive_frames: 2  # cần ít nhất 2 frame liên tiếp
minimum_iou_threshold: 0.20
high_conf_det_threshold: 0.50
```

## 5. Zone Detection

**File config:** `configs/zones.yaml`

**cam_01 — Checkout zones (3 zones):**
```
checkout_queue_01, checkout_queue_02, checkout_queue_03
zone_type: queue
trigger_anchor: bottom_center
polygon định nghĩa bằng tọa độ normalized [0..1]
```

**cam_02 — Aisle zones:**
```
aisle_01      (zone_type: aisle)
promo_area_02 (zone_type: dwell)
aisle_crossing_01  (line, aisle_transition — đếm người đi qua)
```

**Cách hoạt động:** ZoneManager kiểm tra xem `anchor_point` (bottom_center của bbox) có nằm trong polygon không (ray casting algorithm).

## 6. Frame Policy

```yaml
frame_policy:
  mode: tracking_safe     # không drop frame khi tracker đang active
  max_queue_size: 4
  allow_drop: true
  max_consecutive_drops: 3
```

**tracking_safe mode:** ưu tiên không mất frame khi có track active → tránh ID fragmenting.

## 7. Media Output

Vision service ghi ra 3 kênh media:

| Kênh | Cơ chế | Mô tả |
|---|---|---|
| Live JPEG | Redis (`live:frame:bytes:{cam}`) | Annotated JPEG với bbox + zone overlay, TTL ngắn |
| Frame samples | AWS S3 | Upload JPEG samples theo interval (optional) |
| Alert clips | AWS S3 + Pulsar | Video clip khi density vượt threshold |

**Live frame publishing (Redis transport):**
```yaml
live_media_transport: redis
live_redis_host: 52.74.215.164
live_redis_port: 16379
live_media_fps: 15
live_media_jpeg_quality: 75
live_media_ttl_sec: 10
```

## 8. Alert Clip Extraction

**Trigger:** khi số người / frame vượt `alert_density_threshold: 4`

**Cơ chế pre-buffer:**
```yaml
alert_clip_enabled: true
alert_density_threshold: 4
alert_pre_buffer_sec: 3    # giữ 3 giây frame trước khi trigger
alert_post_buffer_sec: 5   # ghi thêm 5 giây sau trigger
alert_cooldown_sec: 30     # chờ 30 giây trước khi trigger tiếp
clip_jpeg_quality: 85
clip_upload_workers: 2
```

**Sau khi tạo clip:**
1. Upload MP4/JPEG clip lên S3: `clips/{date}/{store_id}/{cam_id}/{alert_id}.mp4`
2. Publish event `clip_created` vào Pulsar topic `media-events`
3. API `_media_consumer_loop` nhận event → ghi alert vào Redis

## 9. Pulsar Event Schema

Mỗi frame detection → 1 JSON event publish tới `persistent://retail/metadata/events`:

```json
{
  "schema_version": "1.0",
  "event_id": "cam_01_f001200_20260623_220015",
  "pipeline_run_id": "run_20260623_220000",
  "frame_index": 1200,
  "capture_ts": "2026-06-23T15:00:00.123Z",
  "source": {"store_id": "store_001", "camera_id": "cam_01", "source_type": "video_file"},
  "image_size": {"width": 1920, "height": 1080},
  "detections": [
    {
      "det_id": "1200-0",
      "class": "person", "class_id": 0,
      "conf": 0.87, "track_id": 42,
      "global_track_id": "cam_01_g_000042",
      "bbox": {"x1": 100, "y1": 200, "x2": 300, "y2": 600},
      "zones": [{"zone_id": "checkout_queue_01", "zone_type": "queue", "is_primary": true}],
      "queue": {"in_queue": true, "queue_zone_id": "checkout_queue_01"}
    }
  ],
  "zone_counts": [{"zone_id": "checkout_queue_01", "zone_type": "queue", "count": 3}]
}
```
