Dưới đây là plan build lại **module `services/vision/`** theo hướng production, sử dụng Supervision/Roboflow Trackers như một **Vision Feature Extraction Layer** cho toàn bộ hệ thống Data Engineering của bạn.

Ý chính: **Vision không chỉ detect người nữa**, mà sẽ sinh ra các “facts” có cấu trúc:

```text
person detections
tracked identities
bottom-center anchors
zone membership
line crossings
queue occupancy
debug artifacts
quality metrics
```

Sau đó Pulsar/Flink/Redis/Iceberg/Trino/FastAPI/React tiếp tục xử lý như data platform.

---

# 1. Kết luận quan trọng sau khi đọc tài liệu

## 1.1 Supervision không tự làm detector tốt hơn

Roboflow Trackers docs nói rất rõ: **tracking quality starts at the detector**; nếu detector miss object thì tracker không có cơ hội nối ID. Họ chạy cùng ByteTrack, cùng data, cùng tham số, chỉ đổi detector và kết quả tracking tốt hơn khi detector mạnh hơn. RF-DETR Medium đạt MOTA/HOTA/IDF1 cao hơn RF-DETR Nano và YOLO26 Nano, cho thấy nâng chất lượng detector có thể cải thiện tracking rõ rệt hơn nhiều chỉnh tham số tracker. ([Trackers Roboflow][1]) ([Trackers Roboflow][1])

Vì vậy, lỗi hiện tại của bạn:

```text
detect người bị ngắt quãng → track_id nhảy tùm lum
```

không nên nhìn là “tracker sai” ngay. Có 4 nguyên nhân chính cần xử lý:

```text
1. YOLO miss người vài frame
2. tracker bị reset hoặc không giữ state đúng
3. frame bị drop quá nhiều vì queue size=1
4. người bị che khuất / chuyển động nhanh / bbox dao động
```

Trong tài liệu project của bạn, Vision Service hiện dùng luồng `VideoFileReader → Frame Queue size=1, drop nếu backlog → YOLO11 track → normalize → publish`; đây tốt cho “frame tươi”, nhưng có thể làm tracking khó ổn định nếu inference chậm vì tracker không còn thấy chuỗi frame liên tục. 

---

## 1.2 Supervision giúp chuẩn hóa Vision pipeline

Supervision cung cấp `sv.Detections` để convert output từ nhiều model như Ultralytics YOLO, Roboflow Inference, Transformers… thành một object thống nhất. Docs nói bước normalize này giúp annotator/filter downstream hoạt động giống nhau bất kể nguồn model là gì. ([Roboflow Supervision][2]) ([Roboflow Supervision][2])

Với project của bạn, đây là điểm rất quan trọng:

```text
YOLO11 result
  ↓
sv.Detections
  ↓
filter / track / smooth / zone / line / annotate
  ↓
DetectionFrameEvent JSON
```

Như vậy, sau này bạn có thể thay YOLO11 bằng RF-DETR, YOLOv8/YOLOv11, Roboflow Inference, hoặc model custom mà không phải sửa toàn bộ event builder.

---

## 1.3 Không nên dùng `sv.ByteTrack` cũ trong production mới

Supervision docs hiện ghi `sv.ByteTrack` đã deprecated từ `supervision-0.28.0` và sẽ bị remove ở `supervision-0.30.0`; docs khuyên dùng `ByteTrackTracker` từ package `trackers`, với method `update()` thay cho `update_with_detections()`. ([Roboflow Supervision][3])

Roboflow Trackers docs cũng cho ví dụ production hơn:

```python
from trackers import ByteTrackTracker

tracker = ByteTrackTracker()
detections = tracker.update(detections)
```

và nói tracker chỉ làm ID assignment; detector vẫn cung cấp bbox/mask per-frame. ([Trackers Roboflow][4])

Vì vậy trong module Vision mới, mình khuyên:

```text
supervision = format conversion, annotation, zones, lines, smoothing, sinks
trackers    = ByteTrackTracker / BoT-SORT / OC-SORT
```

---

## 1.4 Count in Zone rất hợp với Retail Analytics

Supervision `PolygonZone` cho phép định nghĩa vùng polygon rồi gọi:

```python
mask = zone.trigger(detections)
```

để biết detection nào đang nằm trong zone. Docs cũng nói PolygonZone web utility dùng để upload một frame/video image rồi lấy tọa độ polygon phục vụ count in zone. ([Roboflow Supervision][5])

Đây chính là nâng cấp từ heatmap grid hiện tại của bạn:

```text
hiện tại:
centroid_norm → heatmap grid 64×48 → zone grid 6×7

sau rebuild:
bottom_center anchor → semantic polygon zone:
checkout_queue_01
entrance
aisle_01
promo_area
cashier_counter
```

Hiện project của bạn đã có normalized bbox/centroid để downstream không phụ thuộc resolution gốc; vậy nên zone config cũng nên dùng normalized polygon points. 

---

## 1.5 Queue monitoring nên là data product của bạn

Bài Roboflow retail queue monitoring dùng computer vision để đo:

```text
số người trong queue
mỗi người ở trong queue bao lâu
queue vượt ngưỡng trong bao lâu
```

Bài viết nói code xử lý video nhưng có thể cấu hình cho realtime system, rất khớp với hệ thống của bạn. ([Roboflow Blog][6])

Tuy nhiên, blog tính `people_enter_queue` và `time_spent` trực tiếp trong Python tutorial. Với hệ thống Data Engineering của bạn, **Vision chỉ nên emit zone/queue facts**, còn dwell time, wait time, session close nên tính bằng Flink vì Flink có keyed state, checkpoint, DLQ và kết nối Redis/Iceberg sẵn có. Project của bạn hiện đã có Flink realtime path và lakehouse path đọc cùng Pulsar topic. 

---

# 2. Kiến trúc tổng thể sau khi rebuild

Hiện tại kiến trúc của bạn là:

```text
Camera / Video
  ↓
Vision Service: YOLO11 + BoTSORT/ByteTrack
  ↓
Pulsar events
  ↓
Flink realtime → Redis
  ↓
Flink lakehouse → Iceberg/S3
  ↓
Trino
  ↓
FastAPI
  ↓
React
```

Vision hiện output Pulsar metadata JSON, annotated JPEG, frame metadata JSON và optional sampled frames lên S3. 

Sau rebuild, kiến trúc nên thành:

```text
Camera / Video / RTSP
  ↓
Vision Service v2
  ├── Frame reader
  ├── Detector: YOLO11 / RF-DETR / custom
  ├── sv.Detections conversion
  ├── Person filtering
  ├── Tracker: ByteTrackTracker / BoT-SORT
  ├── DetectionsSmoother
  ├── Global ID stabilizer
  ├── Bottom-center anchor extraction
  ├── PolygonZone assignment
  ├── LineZone crossing
  ├── Queue snapshot features
  ├── Frame annotation
  ├── Event contract v2 builder
  └── Pulsar publisher + live frame writer + optional debug sinks
        ↓
Pulsar
  ├── events-v2 / metadata events
  ├── media-events
  └── dlq-events
        ↓
Flink Realtime
  ├── ParseValidateV2
  ├── Deduplicate
  ├── Active track state
  ├── Zone occupancy state
  ├── Queue live metrics
  ├── Line crossing counters
  └── Redis sink
        ↓
Redis
  ├── stats:count:{camera_id}
  ├── live:frame:{camera_id}
  ├── track:active:{camera_id}:{global_track_id}
  ├── zone:count:{camera_id}
  ├── queue:live:{camera_id}:{zone_id}
  └── line:count:{camera_id}:{line_id}
        ↓
Flink Lakehouse
  ├── bronze_raw
  ├── silver_detections_v2
  ├── gold_track_summary
  ├── gold_zone_minute_metrics
  ├── gold_queue_sessions
  ├── gold_line_crossing_counts
  └── gold_customer_journey
        ↓
Trino / FastAPI / React
```

Điểm quan trọng: **không phá triết lý hệ thống hiện tại**. Project của bạn đã chọn không lưu raw video vào lakehouse, chỉ trích xuất metadata có cấu trúc, vì metadata nhỏ hơn, queryable và đúng mục tiêu Data Engineering. 

---

# 3. Vai trò mới của Vision Service

Sau rebuild, `services/vision/` không nên chỉ là “YOLO wrapper”. Nó nên là:

> **Edge feature extraction service**: nhận frame, sinh ra metadata giàu ngữ nghĩa, đủ sạch để stream processing và lakehouse analytics.

Vision sẽ chịu trách nhiệm:

```text
1. Đọc frame
2. Detect person
3. Track person
4. Làm mượt bbox/anchor
5. Tính vị trí anchor bottom-center
6. Gán zone_id
7. Ghi nhận line crossing
8. Tạo queue snapshot hiện tại
9. Gửi event schema v2
10. Ghi frame debug cho dashboard
11. Emit metrics về quality/performance
```

Vision **không nên** chịu trách nhiệm chính cho:

```text
1. Tính dwell time lịch sử chuẩn
2. Đóng/mở queue session chuẩn
3. Aggregate hourly/daily
4. Unique visitor dài hạn
5. Business analytics qua ngày
```

Những phần đó nên để Flink + Iceberg làm.

---

# 4. Những chức năng Supervision nên dùng trong module mới

## 4.1 `sv.Detections`

Dùng làm object trung tâm trong toàn bộ Vision pipeline.

```text
YOLO result
  ↓
sv.Detections.from_ultralytics(result)
  ↓
filter person
  ↓
tracker.update(detections)
  ↓
smoother.update_with_detections(detections)
  ↓
zones / lines / annotations / event builder
```

Supervision docs cho biết `sv.Detections.from_ultralytics`, `from_inference`, `from_transformers` giúp convert output model sang object thống nhất. ([Roboflow Supervision][2])

---

## 4.2 Roboflow Trackers

Dùng `trackers.ByteTrackTracker` làm baseline.

Docs của Trackers nói luồng cơ bản là đọc frame, chạy detector, convert sang `sv.Detections`, rồi gọi `tracker.update(detections)` mỗi frame. ([Trackers Roboflow][4])

Config baseline cho retail CCTV:

```yaml
tracker:
  type: bytetrack
  track_activation_threshold: 0.20
  lost_track_buffer: 60
  minimum_consecutive_frames: 2
  frame_rate: 15
```

Giải thích:

| Tham số                      |                   Gợi ý | Lý do                               |
| ---------------------------- | ----------------------: | ----------------------------------- |
| `track_activation_threshold` |               0.20–0.30 | thấp hơn giúp nối detection yếu     |
| `lost_track_buffer`          |                      60 | giữ track sống khi bị che/miss ngắn |
| `minimum_consecutive_frames` |                     2–3 | giảm false track 1 frame            |
| `frame_rate`                 | effective processed FPS | tracker cần time-base gần đúng      |

Supervision docs giải thích `lost_track_buffer` tăng sẽ giúp xử lý occlusion và giảm fragmentation khi mất detection ngắn; `minimum_consecutive_frames` giúp tránh track giả từ false detection/double detection. ([Roboflow Supervision][3])

---

## 4.3 `DetectionsSmoother`

Dùng sau tracker để làm mượt bbox/anchor. Supervision docs nói `DetectionsSmoother` giúp stabilize bounding box coordinates qua các frame. ([Roboflow Supervision][7])

Pipeline đúng:

```text
detections = detector(...)
detections = tracker.update(detections)
detections = smoother.update_with_detections(detections)
```

Không dùng smoother trước tracking.

Smoother không sửa được ID switch nếu tracker đã gán nhầm ID, nhưng nó giúp:

```text
bbox bớt rung
bottom_center anchor bớt nhảy
zone assignment bớt flicker ở ranh giới zone
dashboard nhìn mượt hơn
```

---

## 4.4 `PolygonZone`

Dùng để gán người vào khu vực bán lẻ thực tế:

```text
checkout_queue_01
entrance_area
aisle_01
promo_island
cashier_counter
cold_drink_area
```

Supervision Count in Zone docs dùng `PolygonZone`, `PolygonZoneAnnotator`, `BoxAnnotator`, và gọi `zone.trigger(detections)` để lấy mask các detection nằm trong zone. ([Roboflow Supervision][5])

Trong project của bạn, nên dùng **bottom-center anchor** làm điểm kích hoạt zone vì nó gần vị trí chân hơn centroid. Điều này cũng khớp với paper 3D Person Tracking: họ lấy bottom center pixel của bounding box làm vị trí chân rồi chiếu xuống mặt phẳng sàn. 

---

## 4.5 `LineZone`

Dùng cho:

```text
entrance in/out
queue entry/exit
aisle transition
checkout completed
```

Supervision docs nói `LineZone` trả về `(crossed_in, crossed_out)` và cần `detections.tracker_id`, vì phải match cùng object qua các frame. ([Roboflow Supervision][5])

Vì vậy:

```text
PolygonZone = hiện tại người đang ở đâu
LineZone    = người vừa đi qua ranh giới nào
```

---

## 4.6 Annotators

Dùng cho dashboard/debug:

```text
BoxAnnotator
LabelAnnotator
TraceAnnotator
PolygonZoneAnnotator
LineZoneAnnotator
```

Track Objects docs dùng LabelAnnotator để hiển thị tracker ID/class label và TraceAnnotator để vẽ trajectory lịch sử. ([Roboflow Supervision][7]) ([Roboflow Supervision][7])

Trong project của bạn, annotated frame sẽ tiếp tục ghi vào:

```text
runtime/live_frames/{camera_id}.jpg
runtime/live_frames/{camera_id}.json
```

vì FastAPI hiện có fallback đọc metadata từ file nếu Redis không có data. 

---

## 4.7 `sv.CSVSink` và `sv.JSONSink`

Không dùng làm sink production chính vì production của bạn đã có Pulsar + Iceberg.

Nhưng nên dùng cho:

```text
offline debugging
benchmark tracking
compare detector/tracker configs
export sample detections for thesis evaluation
```

Supervision docs nói `sv.CSVSink` và `sv.JSONSink` dùng để save detections ra `.CSV` và `.JSON` cho offline processing. ([Roboflow Supervision][8])

---

# 5. Kiến trúc module Vision mới

## 5.1 Current module

Theo AGENT.md, hiện `services/vision/` gồm:

```text
main.py
worker.py
reader.py
detect/
track/
emit/
media/
```

và mỗi camera chạy một process riêng, process chính restart worker nếu crash. 

## 5.2 Target module

Production structure nên chuyển sang `src/rva_vision/` để clean packaging, test, import rõ ràng:

```text
services/vision/
├── README.md
├── pyproject.toml
├── Dockerfile
├── Makefile
├── src/
│   └── rva_vision/
│       ├── __init__.py
│       ├── __main__.py
│       ├── main.py
│       ├── app.py
│       ├── cli.py
│       │
│       ├── config/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── loader.py
│       │   ├── validators.py
│       │   ├── camera_config.py
│       │   ├── vision_config.py
│       │   ├── zone_config.py
│       │   └── tracker_config.py
│       │
│       ├── runtime/
│       │   ├── __init__.py
│       │   ├── process_manager.py
│       │   ├── camera_worker.py
│       │   ├── worker_context.py
│       │   ├── lifecycle.py
│       │   └── shutdown.py
│       │
│       ├── sources/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── frame.py
│       │   ├── video_file_source.py
│       │   ├── rtsp_source.py
│       │   ├── webcam_source.py
│       │   ├── frame_queue.py
│       │   ├── frame_sampler.py
│       │   └── timestamp.py
│       │
│       ├── detection/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── yolo_detector.py
│       │   ├── rfdetr_detector.py
│       │   ├── roboflow_detector.py
│       │   ├── detector_factory.py
│       │   ├── slicer.py
│       │   ├── filters.py
│       │   └── nms.py
│       │
│       ├── tracking/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── tracker_factory.py
│       │   ├── bytetrack_adapter.py
│       │   ├── botsort_adapter.py
│       │   ├── smoothing.py
│       │   ├── global_id_stabilizer.py
│       │   ├── track_state.py
│       │   └── track_metrics.py
│       │
│       ├── geometry/
│       │   ├── __init__.py
│       │   ├── anchors.py
│       │   ├── coordinates.py
│       │   ├── normalization.py
│       │   ├── homography.py
│       │   ├── calibration.py
│       │   └── projection.py
│       │
│       ├── zones/
│       │   ├── __init__.py
│       │   ├── polygon_zone_manager.py
│       │   ├── line_zone_manager.py
│       │   ├── zone_assignment.py
│       │   ├── zone_state.py
│       │   └── queue_zone.py
│       │
│       ├── features/
│       │   ├── __init__.py
│       │   ├── frame_features.py
│       │   ├── detection_features.py
│       │   ├── zone_features.py
│       │   ├── line_features.py
│       │   ├── queue_features.py
│       │   └── heatmap_features.py
│       │
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── common.py
│       │   ├── events.py
│       │   ├── detections.py
│       │   ├── zones.py
│       │   ├── lines.py
│       │   ├── queues.py
│       │   ├── runtime.py
│       │   └── validation.py
│       │
│       ├── emit/
│       │   ├── __init__.py
│       │   ├── event_builder.py
│       │   ├── event_id.py
│       │   ├── pulsar_publisher.py
│       │   ├── media_event_publisher.py
│       │   ├── dlq_publisher.py
│       │   ├── debug_sinks.py
│       │   └── serialization.py
│       │
│       ├── media/
│       │   ├── __init__.py
│       │   ├── annotator.py
│       │   ├── overlay.py
│       │   ├── live_frame_writer.py
│       │   ├── snapshot_writer.py
│       │   ├── video_debug_writer.py
│       │   └── s3_frame_uploader.py
│       │
│       ├── observability/
│       │   ├── __init__.py
│       │   ├── logging.py
│       │   ├── metrics.py
│       │   ├── health.py
│       │   ├── profiler.py
│       │   └── quality_reporter.py
│       │
│       └── utils/
│           ├── __init__.py
│           ├── clock.py
│           ├── ids.py
│           ├── cv.py
│           ├── files.py
│           └── errors.py
│
├── tests/
│   ├── unit/
│   │   ├── test_event_builder.py
│   │   ├── test_normalization.py
│   │   ├── test_zone_assignment.py
│   │   ├── test_line_crossing.py
│   │   ├── test_global_id_stabilizer.py
│   │   └── test_config_validation.py
│   ├── integration/
│   │   ├── test_video_to_event_contract.py
│   │   ├── test_pulsar_publish.py
│   │   ├── test_live_frame_writer.py
│   │   └── test_debug_sinks.py
│   ├── fixtures/
│   │   ├── frames/
│   │   ├── videos/
│   │   ├── detections/
│   │   └── configs/
│   └── e2e/
│       ├── test_single_camera_pipeline.py
│       └── test_multi_camera_pipeline.py
│
└── scripts/
    ├── extract_first_frame.py
    ├── validate_zones.py
    ├── benchmark_tracker.py
    ├── export_debug_detections.py
    ├── compare_tracker_configs.py
    └── run_offline_video.py
```

---

# 6. Config production nên có

## 6.1 `configs/cameras.yaml`

Giữ file hiện tại, nhưng thêm `vision_profile`, `zone_profile`, `tracker_profile`.

```yaml
cameras:
  - camera_id: cam_01
    store_id: store_001
    source_type: video_file
    source_uri: data/videos/store_cam_01.mp4
    enabled: true

    resolution:
      width: 1280
      height: 720

    vision_profile: retail_yolo11_default
    tracker_profile: bytetrack_retail_stable
    zone_profile: store_001_cam_01_zones

    runtime:
      process_mode: dedicated_process
      restart_on_crash: true
      max_restart_backoff_sec: 30
```

---

## 6.2 `configs/vision.yaml`

```yaml
profiles:
  retail_yolo11_default:
    detector:
      type: ultralytics_yolo
      model_path: yolo11l.pt
      device: cuda
      classes: [0]
      conf: 0.15
      iou: 0.70
      imgsz: 1280
      half: true
      agnostic_nms: false

    slicer:
      enabled: false
      slice_wh: [640, 640]
      overlap_wh: [120, 120]
      iou_threshold: 0.50

    output:
      publish_every_frame: true
      write_live_frame_every_n: 1
      write_debug_json: true
      sample_frames_to_s3: false

    frame_policy:
      mode: tracking_safe
      max_queue_size: 4
      max_frame_lag_ms: 500
      allow_drop: true
      max_consecutive_drops: 3
```

Quan trọng: thay vì `queue size=1` cho mọi mode, nên có 2 mode:

```text
latest_only      → demo realtime, ít latency, tracking dễ nhảy
tracking_safe    → giữ chuỗi frame ổn hơn, chấp nhận delay nhỏ
```

---

## 6.3 `configs/trackers.yaml`

```yaml
profiles:
  bytetrack_retail_stable:
    type: bytetrack
    track_activation_threshold: 0.20
    lost_track_buffer: 60
    minimum_consecutive_frames: 2
    frame_rate: 15

    global_id:
      enabled: true
      max_reconnect_gap_ms: 2000
      max_reconnect_distance_px: 120
      max_bbox_area_ratio_delta: 0.50
      require_same_or_adjacent_zone: true

    smoothing:
      enabled: true
      length: 5
```

---

## 6.4 `configs/zones.yaml`

Dùng PolygonZone web utility để lấy tọa độ polygon. Docs yêu cầu upload image/frame từ video để lấy tọa độ; PolygonZone trả về NumPy arrays để dùng với Supervision. ([Roboflow Supervision][5])

Nên lưu **normalized polygon**:

```yaml
version: "zones-2026-06-02-v1"

stores:
  store_001:
    cameras:
      cam_01:
        resolution:
          width: 1280
          height: 720

        zones:
          - zone_id: checkout_queue_01
            zone_name: Checkout Queue 01
            zone_type: queue
            priority: 100
            trigger_anchor: bottom_center
            polygon_norm:
              - [0.55, 0.42]
              - [0.92, 0.44]
              - [0.96, 0.88]
              - [0.50, 0.90]

          - zone_id: promo_area_01
            zone_name: Promotion Area
            zone_type: dwell
            priority: 50
            trigger_anchor: bottom_center
            polygon_norm:
              - [0.10, 0.35]
              - [0.40, 0.34]
              - [0.45, 0.82]
              - [0.08, 0.85]

          - zone_id: entrance_area
            zone_name: Main Entrance Area
            zone_type: entrance
            priority: 80
            trigger_anchor: bottom_center
            polygon_norm:
              - [0.02, 0.60]
              - [0.35, 0.58]
              - [0.38, 0.98]
              - [0.00, 0.98]

        lines:
          - line_id: entrance_line_01
            line_name: Main Entrance Line
            line_type: entrance_exit
            start_norm: [0.05, 0.78]
            end_norm: [0.35, 0.74]
            direction_in: left_to_right

          - line_id: queue_entry_line_01
            line_name: Queue Entry Line
            line_type: queue_entry
            start_norm: [0.50, 0.60]
            end_norm: [0.78, 0.58]
            direction_in: top_to_bottom
```

---

# 7. Pipeline xử lý trong Vision Service v2

## 7.1 Per-camera worker lifecycle

```text
main.py
  ↓
load cameras.yaml
  ↓
for each enabled camera:
    spawn CameraWorker process
  ↓
CameraWorker:
    load camera config
    load vision profile
    load tracker profile
    load zone profile
    init detector
    init tracker
    init smoother
    init zone managers
    init publishers
    init live frame writer
    run frame loop
```

Tracker phải được khởi tạo **một lần cho mỗi camera worker**, không được tạo lại mỗi frame.

---

## 7.2 Frame loop

```python
while running:
    frame_packet = source.read()

    result = detector.predict(frame_packet.image)

    detections = sv.Detections.from_ultralytics(result)
    detections = person_filter.apply(detections)

    detections = tracker.update(detections)
    detections = smoother.update_with_detections(detections)

    anchors = anchor_extractor.bottom_center(detections)

    global_ids = global_id_stabilizer.update(
        detections=detections,
        anchors=anchors,
        capture_ts=frame_packet.capture_ts,
    )

    zone_result = polygon_zone_manager.assign(
        detections=detections,
        anchors=anchors,
        global_ids=global_ids,
    )

    line_result = line_zone_manager.trigger(
        detections=detections,
        global_ids=global_ids,
    )

    frame_features = feature_builder.build(
        detections=detections,
        anchors=anchors,
        zones=zone_result,
        lines=line_result,
    )

    event = event_builder.build_detection_frame_event(frame_features)

    pulsar_publisher.publish(event)

    annotated = annotator.draw(frame_packet.image, frame_features)
    live_frame_writer.write(camera_id, annotated, event)
```

---

# 8. Event contract v2

Event hiện tại có `schema_version`, `event_id`, `pipeline_run_id`, `frame_index`, `capture_ts`, `source`, `image_size`, `detections`, và `runtime`. 

Nên nâng lên v2 như sau.

## 8.1 Frame event

```json
{
  "schema_version": "2.0",
  "event_type": "detection_frame",
  "event_id": "uuid-deterministic",
  "pipeline_run_id": "vision-run-20260602-001",
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
    "zone_config_version": "zones-2026-06-02-v1"
  },

  "frame_metrics": {
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
  },

  "zone_counts": [
    {
      "zone_id": "checkout_queue_01",
      "zone_type": "queue",
      "count": 3,
      "track_ids": [12, 18, 21],
      "global_track_ids": ["cam_01_g_000012", "cam_01_g_000018", "cam_01_g_000021"]
    }
  ],

  "line_crossings": [
    {
      "line_id": "entrance_line_01",
      "line_type": "entrance_exit",
      "direction": "in",
      "track_id": 12,
      "global_track_id": "cam_01_g_000012"
    }
  ],

  "detections": []
}
```

---

## 8.2 Detection object

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

---

# 9. Global Track ID Stabilizer

Vì bạn đang gặp ID nhảy, phần này rất quan trọng.

## 9.1 Tách `track_id` và `global_track_id`

```text
track_id
  = ID thô từ ByteTrack/BoT-SORT

global_track_id
  = ID ổn định của hệ thống bạn
```

Ví dụ:

```text
track_id: 12  → global_track_id: cam_01_g_000001
track_id: 31  → global_track_id: cam_01_g_000001
```

Nghĩa là tracker bị đứt, sinh ID mới `31`, nhưng hệ thống nhận ra đó vẫn là người cũ.

## 9.2 Merge rule

Khi một track mới xuất hiện:

```text
Tìm lost track gần đây trong 0.5–2.0 giây
  nếu last_anchor gần first_anchor
  và bbox size tương tự
  và zone giống nhau hoặc liền kề
  và hướng di chuyển hợp lý
→ reuse global_track_id
```

Pseudo:

```python
def try_reconnect(new_track, recently_lost_tracks):
    candidates = []

    for old in recently_lost_tracks:
        time_gap_ms = new_track.first_seen_ts - old.last_seen_ts
        if time_gap_ms > max_reconnect_gap_ms:
            continue

        distance = euclidean(new_track.anchor, old.anchor)
        if distance > max_reconnect_distance_px:
            continue

        if not similar_bbox_size(new_track.bbox, old.bbox):
            continue

        if require_same_or_adjacent_zone:
            if not zones_compatible(new_track.zone_id, old.zone_id):
                continue

        score = compute_reconnect_score(old, new_track)
        candidates.append((score, old))

    if candidates:
        return best_candidate.global_track_id

    return allocate_new_global_track_id()
```

## 9.3 Dùng world coordinate sau này

Khi bạn bổ sung camera calibration/homography, nên merge bằng mét thay vì pixel:

```text
distance_px  → distance_meter
```

Paper 3D Person Tracking cũng dùng bottom-center của bbox, giả định chân trên mặt sàn `Z=0`, rồi ánh xạ sang world coordinate. 

---

# 10. Redis realtime sau rebuild

Hiện Redis của bạn có:

```text
stats:count:{camera_id}
live:frame:{camera_id}
heatmap:live:{camera_id}
track:active:{camera_id}:{track_id}
```

với TTL ngắn để dashboard tự chuyển warning khi pipeline dừng. 

Nên mở rộng thành:

## 10.1 Existing keys giữ nguyên

```text
stats:count:{camera_id}
live:frame:{camera_id}
heatmap:live:{camera_id}
```

## 10.2 Active track key đổi sang global ID

```text
track:active:{camera_id}:{global_track_id}
```

Hash fields:

```text
track_id
global_track_id
last_seen_ts
current_zone_id
anchor_x_norm
anchor_y_norm
bbox
conf
track_age_sec
zone_enter_ts
quality_flags
```

## 10.3 Zone count

```text
zone:count:{camera_id}
```

Redis Hash:

```text
HSET zone:count:cam_01 checkout_queue_01 3 promo_area_01 1 entrance_area 2
EXPIRE zone:count:cam_01 10
```

## 10.4 Queue live

```text
queue:live:{camera_id}:{zone_id}
```

Redis Hash:

```text
current_count
oldest_wait_sec
avg_wait_sec
max_wait_sec
threshold_status
oldest_global_track_id
last_update_ts
```

## 10.5 Line counts

```text
line:count:{camera_id}:{line_id}:{window}
```

Ví dụ:

```text
line:count:cam_01:entrance_line_01:5m
  in_count
  out_count
```

---

# 11. Flink thay đổi như thế nào?

## 11.1 Realtime job

Hiện realtime job parse/validate, deduplicate, ghi Redis và DLQ. 

Sau rebuild:

```text
RealtimeMetricsJobV2
  ├── ParseValidateV2
  ├── Deduplicate by event_id
  ├── Extract detections
  ├── Update active tracks
  ├── Update zone counts
  ├── Update queue live metrics
  ├── Update line counts
  ├── Write Redis
  └── Invalid → DLQ
```

## 11.2 QueueSessionJob

Key:

```text
store_id + camera_id + zone_id + global_track_id
```

State:

```text
is_in_queue
enter_ts
last_seen_ts
frame_count
max_conf
last_track_id
```

Logic:

```text
Nếu detection.in_queue == true và chưa có session:
  emit queue_session_started

Nếu detection.in_queue == true và session đang mở:
  update last_seen_ts, frame_count

Nếu không thấy người trong queue quá grace_period:
  emit queue_session_closed
  wait_time_sec = last_seen_ts - enter_ts
```

Grace period nên có để tránh zone flicker:

```yaml
queue:
  exit_grace_ms: 2000
  min_session_ms: 3000
```

## 11.3 ZoneMinuteMetricsJob

Window:

```text
Tumbling event-time window 1 minute
```

Output:

```sql
store_id
camera_id
zone_id
window_start
window_end
avg_occupancy
max_occupancy
unique_global_tracks
detection_count
```

## 11.4 LineCrossingAggregationJob

Input:

```text
line_crossings[]
```

Output:

```sql
store_id
camera_id
line_id
window_start
window_end
in_count
out_count
net_count
```

---

# 12. Iceberg/Lakehouse sau rebuild

Hiện bạn có:

```text
bronze_raw
silver_detections
gold_track_summary
```

trên Iceberg/S3, query bằng Trino. 

Sau rebuild, nên giữ Bronze nhưng nâng Silver và Gold.

## 12.1 Bronze

```sql
lakehouse.rva.bronze_raw
```

Giữ raw event JSON v2.

Thêm extracted headers:

```sql
schema_version
event_type
event_id
pipeline_run_id
store_id
camera_id
capture_ts
ingest_ts
zone_config_version
model_name
tracker_type
```

## 12.2 Silver detections v2

```sql
lakehouse.rva.silver_detections_v2
```

Columns:

```sql
store_id
camera_id
capture_ts
frame_index
source_frame_index
det_id
class_id
class_name
conf

track_id
global_track_id
track_status

bbox_x1
bbox_y1
bbox_x2
bbox_y2
bbox_x_norm
bbox_y_norm
bbox_w_norm
bbox_h_norm

centroid_x
centroid_y
centroid_x_norm
centroid_y_norm

anchor_type
anchor_x
anchor_y
anchor_x_norm
anchor_y_norm

primary_zone_id
primary_zone_type
in_queue
queue_zone_id

model_name
detector_type
tracker_type
supervision_version
trackers_version
zone_config_version

processing_total_ms
inference_ms
tracking_ms
zone_ms
```

Partition:

```sql
PARTITIONED BY (
  store_id,
  bucket(16, camera_id),
  days(capture_ts)
)
```

## 12.3 Silver line crossings

```sql
lakehouse.rva.silver_line_crossings
```

```sql
store_id
camera_id
capture_ts
frame_index
line_id
line_type
direction
track_id
global_track_id
zone_config_version
```

## 12.4 Gold tables mới

### `gold_zone_minute_metrics`

```sql
store_id
camera_id
zone_id
zone_type
window_start
window_end
avg_occupancy
max_occupancy
unique_visitors
detection_count
```

### `gold_queue_sessions`

```sql
store_id
camera_id
queue_zone_id
global_track_id
enter_ts
exit_ts
wait_time_sec
frame_count
completed
exit_reason
```

### `gold_line_crossing_counts`

```sql
store_id
camera_id
line_id
line_type
window_start
window_end
in_count
out_count
net_count
```

### `gold_customer_journey`

```sql
store_id
camera_id
global_track_id
from_zone_id
to_zone_id
transition_ts
dwell_before_transition_sec
```

### `gold_camera_health_minute`

```sql
store_id
camera_id
window_start
window_end
source_fps_avg
effective_fps_avg
dropped_frames
inference_ms_p50
inference_ms_p95
tracking_ms_p95
event_publish_failures
```

Những Gold tables này khớp roadmap Phase 2/3 hiện tại của bạn, nơi project còn thiếu Gold tables mới và FastAPI analytics endpoints gọi Trino. 

---

# 13. FastAPI và React sau rebuild

## 13.1 FastAPI live endpoint

Endpoint hiện tại:

```text
GET /api/v1/live/{camera_id}/dashboard
```

nên mở rộng response:

```json
{
  "camera_id": "cam_01",
  "people_count": 8,
  "frame": {
    "capture_ts": "...",
    "effective_fps": 12.4,
    "inference_ms": 68,
    "tracking_ms": 4
  },
  "zones": [
    {
      "zone_id": "checkout_queue_01",
      "zone_name": "Checkout Queue 01",
      "zone_type": "queue",
      "current_count": 3,
      "status": "warning",
      "avg_wait_sec": 42,
      "max_wait_sec": 91
    }
  ],
  "lines": [
    {
      "line_id": "entrance_line_01",
      "in_count_last_5m": 15,
      "out_count_last_5m": 9
    }
  ],
  "tracks": [
    {
      "global_track_id": "cam_01_g_000042",
      "track_id": 31,
      "zone_id": "checkout_queue_01",
      "anchor_x_norm": 0.52,
      "anchor_y_norm": 0.78,
      "queue_wait_sec": 36
    }
  ]
}
```

## 13.2 New API endpoints

```text
GET /api/v1/live/{camera_id}/zones
GET /api/v1/live/{camera_id}/queues
GET /api/v1/live/{camera_id}/tracks
GET /api/v1/analytics/zones
GET /api/v1/analytics/queues
GET /api/v1/analytics/traffic
GET /api/v1/analytics/customer-journey
GET /api/v1/system/vision/{camera_id}
```

## 13.3 React Live page

Nên hiển thị:

```text
1. Annotated live frame
2. Polygon overlays
3. Line overlays
4. Track trails
5. Current people count
6. Queue count
7. Oldest queue wait
8. Zone occupancy cards
9. Camera quality warning:
   - low FPS
   - high dropped frames
   - high ID switch estimate
```

---

# 14. Tracking stability plan

Đây là phần cần làm rất nghiêm túc vì bạn đang bị ID nhảy.

## 14.1 Baseline measurement trước khi sửa

Tạo script:

```text
services/vision/scripts/benchmark_tracker.py
```

Output CSV:

```text
frame_index
source_frame_index
capture_ts
raw_detection_count
tracked_detection_count
track_ids
new_track_ids
lost_track_ids
dropped_frames
effective_fps
inference_ms
tracking_ms
```

Nếu có video test, export thêm annotated video bằng `TraceAnnotator`.

## 14.2 Kiểm tra detector

Nếu detector miss nhiều:

```text
num_raw_detections = 0 nhưng người vẫn trong frame
```

thì tracker không thể cứu. Docs đã nói tracking quality starts at detector. ([Trackers Roboflow][1])

Action:

```text
1. tăng imgsz lên 1280 hoặc 1536
2. giảm detector conf xuống 0.10–0.20
3. chỉ filter class person
4. bật slicer cho camera wide-angle
5. fine-tune model bằng frame retail của bạn
6. cân nhắc RF-DETR nếu YOLO miss người nhỏ/xa
```

## 14.3 Kiểm tra frame dropping

Nếu:

```text
effective_fps thấp
dropped_frames cao
ID nhảy khi người di chuyển nhanh
```

Action:

```text
1. chuyển frame_policy từ latest_only sang tracking_safe
2. tăng queue max size từ 1 lên 4–8
3. giới hạn max consecutive drops
4. log source_frame_index và dropped_frames_since_last
5. dùng GPU / half precision / model nhỏ hơn nếu cần
```

## 14.4 Tune tracker

Baseline:

```yaml
track_activation_threshold: 0.20
lost_track_buffer: 60
minimum_consecutive_frames: 2
frame_rate: effective_fps
```

Nếu ID hay mất khi người bị che:

```text
tăng lost_track_buffer: 60 → 90
```

Nếu nhiều track giả:

```text
tăng minimum_consecutive_frames: 2 → 3 hoặc 5
```

Nếu người đứng sát nhau bị swap ID:

```text
thử BoT-SORT / ReID sau khi ByteTrack baseline ổn
```

## 14.5 Global ID stabilizer

Bắt buộc nếu muốn:

```text
dwell time
queue wait time
unique visitor
customer journey
```

Không nên dùng raw `track_id` để tính business metrics.

---

# 15. Production coding interfaces

## 15.1 Detector interface

```python
from typing import Protocol
import numpy as np
import supervision as sv


class Detector(Protocol):
    def predict(self, frame: np.ndarray) -> sv.Detections:
        ...
```

## 15.2 Tracker interface

```python
class MultiObjectTracker(Protocol):
    def update(self, detections: sv.Detections) -> sv.Detections:
        ...

    def reset(self) -> None:
        ...
```

## 15.3 Zone manager interface

```python
@dataclass
class ZoneAssignment:
    detection_index: int
    zone_id: str
    zone_type: str
    is_primary: bool


class PolygonZoneManager:
    def assign(self, detections: sv.Detections) -> list[ZoneAssignment]:
        ...
```

## 15.4 Event builder interface

```python
class DetectionFrameEventBuilder:
    def build(
        self,
        frame_packet: FramePacket,
        detections: sv.Detections,
        global_ids: list[str],
        anchors: list[Anchor],
        zone_assignments: list[ZoneAssignment],
        line_crossings: list[LineCrossing],
        runtime_metrics: RuntimeMetrics,
    ) -> DetectionFrameEvent:
        ...
```

---

# 16. Implementation roadmap cực chi tiết

## Phase 0 — Baseline hiện trạng

Mục tiêu: biết chính xác hệ thống đang fail ở đâu.

Tasks:

```text
1. Thêm logging cho Vision hiện tại:
   - source_frame_index
   - processed_frame_index
   - dropped_frames_since_last
   - raw_detection_count
   - track_ids
   - new/lost track ids
   - inference_ms
   - tracking_ms
   - effective_fps

2. Chạy 3 video test:
   - ít người, không che
   - checkout queue
   - đông người/occlusion

3. Export annotated debug video.

4. Ghi baseline:
   - avg track duration
   - số lần ID switch ước lượng
   - detection miss rate thủ công trên 100 frame
   - effective FPS
```

Acceptance:

```text
Có file report baseline.
Biết ID nhảy do detector miss, frame drop, tracker reset hay occlusion.
```

---

## Phase 1 — Thay core detection output bằng `sv.Detections`

Mục tiêu: chưa đổi downstream, chỉ refactor Vision nội bộ.

Tasks:

```text
1. Tạo detection/base.py
2. Tạo detection/yolo_detector.py
3. Convert YOLO result → sv.Detections.from_ultralytics
4. Filter class_id == 0
5. Build event contract v1 y như cũ từ sv.Detections
6. Đảm bảo Pulsar event không đổi schema
7. Đảm bảo FastAPI/React không vỡ
```

Acceptance:

```text
Redis stats:count vẫn có data.
live_frame vẫn có bbox.
silver_detections vẫn ghi được.
Không đổi event schema v1.
```

---

## Phase 2 — Tracker mới bằng `trackers.ByteTrackTracker`

Mục tiêu: tracking state rõ ràng, không reset mỗi frame.

Tasks:

```text
1. Thêm dependency trackers
2. Tạo tracking/tracker_factory.py
3. Tạo tracking/bytetrack_adapter.py
4. Tracker instance sống theo CameraWorker
5. Chỉ reset khi camera restart/source restart
6. Tune lost_track_buffer/minimum_consecutive_frames
7. Thêm DetectionsSmoother
8. Thêm TraceAnnotator cho debug frame
```

Acceptance:

```text
Cùng một video baseline, avg track duration tăng.
Số track_id mới vô lý giảm.
Không còn trường hợp tracker reset từng frame.
```

---

## Phase 3 — Frame policy mới

Mục tiêu: giảm ID nhảy do drop frame quá mạnh.

Tasks:

```text
1. Thêm frame_policy trong configs/vision.yaml
2. Implement tracking_safe queue:
   - queue max size 4–8
   - drop có kiểm soát
   - log skipped source frame
3. Implement latest_only mode cho demo latency thấp
4. Ghi dropped_frames_since_last vào event
5. Set frame_rate tracker theo effective FPS
```

Acceptance:

```text
Tracking_safe có ID ổn hơn latest_only.
Latency vẫn chấp nhận được cho dashboard.
Event có source_frame_index và dropped_frames_since_last.
```

---

## Phase 4 — Zone config + PolygonZone

Mục tiêu: từ heatmap pixel sang semantic retail zones.

Tasks:

```text
1. Tạo configs/zones.yaml
2. Tạo scripts/extract_first_frame.py
3. Dùng PolygonZone web utility để vẽ zone
4. Tạo zones/polygon_zone_manager.py
5. Convert polygon_norm → polygon_px
6. Gọi zone.trigger(detections)
7. Gán primary_zone_id cho detection
8. Tính zone_counts frame-level
9. Annotate polygon overlay lên live frame
```

Acceptance:

```text
Event có zone_counts.
Detection có zones[].
Live frame có overlay polygon.
Redis chưa cần đổi ở phase này nếu muốn giảm risk.
```

---

## Phase 5 — LineZone

Mục tiêu: entrance/exit và queue entry/exit.

Tasks:

```text
1. Thêm lines vào zones.yaml
2. Tạo zones/line_zone_manager.py
3. Gọi LineZone sau tracking
4. Emit line_crossings[]
5. Annotate line overlay
6. Test với video người đi qua entrance
```

Acceptance:

```text
Event có line_crossings[].
Direction in/out đúng trên video test.
Không tính double-crossing quá nhiều.
```

---

## Phase 6 — Event contract v2

Mục tiêu: chính thức version hóa data contract.

Tasks:

```text
1. Tạo schemas/events.py bằng Pydantic
2. schema_version = "2.0"
3. Thêm event_type
4. Thêm frame_metrics
5. Thêm zone_counts
6. Thêm line_crossings
7. Thêm detection.anchor
8. Thêm detection.zones
9. Thêm global_track_id
10. Update ParseValidate Flink để accept v1 và v2 trong giai đoạn migration
```

Acceptance:

```text
Pulsar nhận event v2.
Flink không crash.
DLQ không tăng bất thường.
Bronze raw lưu đủ payload.
```

---

## Phase 7 — Redis realtime v2

Mục tiêu: dashboard live có zone/queue/line.

Tasks:

```text
1. Update RealtimeRedisSink:
   - zone:count:{camera_id}
   - queue:live:{camera_id}:{zone_id}
   - line:count:{camera_id}:{line_id}
   - track:active by global_track_id

2. Update FastAPI live schema.

3. Update React Live page:
   - zone cards
   - queue count
   - longest wait
   - line crossing counters
```

Acceptance:

```text
Live page hiển thị current zone count.
Queue zone hiển thị current_count.
Entrance line hiển thị in/out.
TTL hoạt động khi dừng camera.
```

---

## Phase 8 — Queue sessions bằng Flink

Mục tiêu: wait time/dwell time chính xác hơn.

Tasks:

```text
1. Tạo QueueSessionJob hoặc mở rộng GoldTrackSummaryJob
2. Key by camera_id + zone_id + global_track_id
3. Maintain enter_ts, last_seen_ts, frame_count
4. Exit grace 2s
5. Emit completed queue session
6. Sink Redis live queue metrics
7. Sink Iceberg gold_queue_sessions
```

Acceptance:

```text
gold_queue_sessions có rows.
wait_time_sec hợp lý khi xem lại video.
Queue session không bị split quá nhiều khi ID nhảy nhẹ.
```

---

## Phase 9 — Lakehouse Gold zone analytics

Mục tiêu: Analytics page có data thật.

Tasks:

```text
1. silver_detections_v2
2. silver_line_crossings
3. gold_zone_minute_metrics
4. gold_line_crossing_counts
5. gold_customer_journey
6. Trino validation queries
7. FastAPI analytics endpoints
```

Acceptance:

```text
Trino query được:
- top crowded zones
- avg wait by hour
- entrance traffic by 5-min window
- dwell time by zone
```

---

## Phase 10 — Observability & production hardening

Tasks:

```text
1. Prometheus-style metrics:
   - vision_frames_processed_total
   - vision_inference_ms
   - vision_tracking_ms
   - vision_publish_failures_total
   - vision_dropped_frames_total
   - vision_active_tracks
   - vision_new_tracks_total
   - vision_lost_tracks_total

2. Structured logs JSON.

3. Health endpoint per worker.

4. Dead-letter local spool nếu Pulsar down.

5. Graceful shutdown:
   - flush publisher
   - close video capture
   - write final health state

6. Backpressure policy:
   - when Pulsar slow
   - when GPU overloaded
   - when S3 upload slow
```

Acceptance:

```text
Có metrics để debug camera nào yếu.
Restart worker không làm treo process manager.
Pulsar down không crash loop liên tục.
```

---

# 17. Test strategy

## 17.1 Unit tests

```text
test_normalization.py
  bbox pixel → bbox_norm đúng

test_anchor.py
  bbox → bottom_center đúng

test_zone_assignment.py
  anchor trong polygon → zone_id đúng

test_line_crossing.py
  same tracker_id đi qua line → crossed_in/out đúng

test_event_builder.py
  event v2 valid schema

test_global_id_stabilizer.py
  track đứt 1s, xuất hiện gần → same global_track_id
```

## 17.2 Integration tests

```text
test_video_to_event_contract.py
  video fixture → list event v2

test_pulsar_publish.py
  publish local Pulsar topic

test_live_frame_writer.py
  sinh cam_01.jpg và cam_01.json

test_debug_sinks.py
  CSV/JSON sink ghi đúng columns
```

## 17.3 E2E tests

```text
docker compose up
run vision on sample video
check Pulsar events
check Redis keys
check Iceberg bronze/silver/gold
check FastAPI dashboard
```

Bạn đã có checklist verify pipeline hiện tại gồm Vision frame, Pulsar stats, Flink jobs, Redis, Heatmap, Bronze/Silver/Gold, API endpoint và S3 Iceberg. Có thể mở rộng checklist đó cho zone/queue/line. 

---

# 18. Những chỉ số nên đưa vào luận văn

## Vision quality metrics

```text
processed_fps
dropped_frames_per_min
avg_inference_ms
p95_inference_ms
avg_tracking_ms
num_raw_detections
num_tracked_detections
track_fragmentation_estimate
avg_track_duration_sec
```

## Retail analytics metrics

```text
current_people_count
zone_occupancy
queue_length
avg_queue_wait_sec
max_queue_wait_sec
entrance_in_count
entrance_out_count
zone_dwell_time
customer_journey transitions
```

## Data Engineering metrics

```text
Pulsar event throughput
Flink processing latency
Redis update latency
Iceberg commit latency
DLQ rate
schema validation error rate
end-to-end latency camera → dashboard
```

Phase 6 trong roadmap của bạn đã có mục tiêu đo latency end-to-end và GPU/CPU resource metrics, nên các chỉ số này rất hợp để đưa vào evaluation plan. 

---

# 19. Phân quyền logic: Vision vs Flink

Đây là ranh giới mình khuyên giữ rõ:

| Logic                       |           Nên nằm ở Vision | Nên nằm ở Flink |
| --------------------------- | -------------------------: | --------------: |
| Detect person               |                         Có |           Không |
| Convert `sv.Detections`     |                         Có |           Không |
| Track ID thô                |                         Có |           Không |
| Global ID reconnect ngắn    |                     Có thể |  Có thể bổ sung |
| Bottom-center anchor        |                         Có |           Không |
| Polygon zone assignment     |                         Có |           Không |
| Line crossing instant event |                         Có |           Không |
| Current frame zone count    |                         Có |    Có thể cache |
| Queue session duration      |                  Không nên |              Có |
| Dwell time                  |                  Không nên |              Có |
| Minute/hour/day aggregate   |                      Không |              Có |
| Redis live serving          | Không trực tiếp, qua event |              Có |
| Iceberg history             |                      Không |              Có |

Lý do: Vision worker có thể restart, mất Python memory state. Flink có checkpoint và state TTL, phù hợp hơn để tính session, dwell và aggregate.

---

# 20. Plan dependency update

Trong `pyproject.toml` hoặc workspace package của `rva-vision`, thêm:

```toml
dependencies = [
  "ultralytics",
  "supervision",
  "trackers",
  "opencv-python",
  "numpy",
  "pydantic",
  "pydantic-settings",
  "orjson",
  "prometheus-client",
  "pulsar-client",
  "boto3"
]
```

Nếu GPU:

```toml
optional-dependencies.gpu = [
  "torch",
  "torchvision"
]
```

Nếu thử Roboflow Inference/RF-DETR:

```toml
optional-dependencies.roboflow = [
  "inference",
  "inference-models"
]
```

---

# 21. Rủi ro và cách giảm rủi ro

## Rủi ro 1: Supervision/Trackers API thay đổi

Giảm rủi ro:

```text
1. Pin version trong uv.lock
2. Tạo adapter layer nội bộ
3. Không gọi trực tiếp Supervision khắp codebase
```

Ví dụ:

```text
tracking/bytetrack_adapter.py
zones/polygon_zone_manager.py
media/annotator.py
```

Nếu API đổi, chỉ sửa adapter.

---

## Rủi ro 2: ID vẫn nhảy dù đổi tracker

Giảm rủi ro:

```text
1. Đo detector miss rate
2. Giảm frame drop
3. Tune tracker
4. Thêm global_track_id
5. Tính queue/dwell bằng Flink với grace period
```

---

## Rủi ro 3: Zone flicker ở ranh giới

Giảm rủi ro:

```text
1. dùng bottom-center anchor
2. dùng smoother
3. zone priority nếu zones overlap
4. Flink exit grace 1–2 giây
5. chỉ đổi zone nếu stable N frame
```

---

## Rủi ro 4: Vision quá nặng, FPS thấp

Giảm rủi ro:

```text
1. model profile theo camera
2. YOLO11n/s cho camera phụ, YOLO11l cho camera quan trọng
3. imgsz theo camera
4. bật slicer chỉ khi cần
5. GPU half precision
6. không upload S3 frame quá thường xuyên
```

---

# 22. Bản thiết kế cuối cùng nên ghi trong docs

Bạn nên thêm các tài liệu mới:

```text
docs/14_VISION_SUPERVISION_REBUILD.md
docs/15_ZONE_AND_QUEUE_ANALYTICS_DESIGN.md
docs/16_EVENT_CONTRACT_V2.md
docs/17_TRACKING_QUALITY_EVALUATION.md
docs/18_REDIS_LIVE_SERVING_V2.md
docs/19_ICEBERG_ZONE_QUEUE_GOLD_TABLES.md
```

Trong luận văn, phần này sẽ rất mạnh vì bạn chứng minh được:

```text
Computer Vision chỉ là source extractor
Data Engineering mới là trung tâm:
  event contract
  stream processing
  realtime serving
  lakehouse modeling
  analytics product
  observability
```

---

# 23. Tóm tắt quyết định kỹ thuật cuối cùng

Mình đề xuất bạn build lại `services/vision/` theo hướng này:

```text
1. Dùng Supervision làm chuẩn trung gian:
   YOLO/RF-DETR → sv.Detections

2. Dùng Roboflow Trackers thay `sv.ByteTrack` cũ:
   ByteTrackTracker.update(detections)

3. Dùng DetectionsSmoother sau tracker:
   giảm bbox/anchor jitter

4. Dùng bottom-center anchor:
   tốt hơn centroid cho retail zone và tracking vị trí chân

5. Dùng PolygonZone cho semantic zones:
   checkout, aisle, entrance, promo area

6. Dùng LineZone cho entrance/exit và queue crossing:
   cần tracker_id ổn định

7. Thêm global_track_id:
   không dùng raw track_id cho business metrics

8. Vision chỉ emit facts:
   detections, tracks, zones, lines, queue snapshot

9. Flink tính sessions:
   queue wait time, dwell time, customer journey

10. Redis phục vụ live:
   zone count, queue live, line counters

11. Iceberg phục vụ historical analytics:
   silver_detections_v2, gold_queue_sessions, gold_zone_minute_metrics
```

Nếu thực hiện theo plan này, project của bạn sẽ chuyển từ:

```text
YOLO + tracking + heatmap
```

thành:

```text
Retail Video Analytics Data Platform
  có realtime queue monitoring
  có semantic zone analytics
  có customer journey
  có lakehouse historical analytics
  có tracking quality evaluation
```

Đây là hướng rất phù hợp cho đồ án tốt nghiệp Data Engineering, vì Supervision giúp chuẩn hóa phần vision, còn phần có giá trị học thuật/kỹ thuật chính nằm ở **streaming data product, event contract, stateful processing, Redis realtime serving, Iceberg lakehouse và Trino analytics**.

[1]: https://trackers.roboflow.com/develop/learn/detection-quality/ "https://trackers.roboflow.com/develop/learn/detection-quality/"
[2]: https://supervision.roboflow.com/develop/how_to/detect_and_annotate/ "https://supervision.roboflow.com/develop/how_to/detect_and_annotate/"
[3]: https://supervision.roboflow.com/develop/trackers/ "https://supervision.roboflow.com/develop/trackers/"
[4]: https://trackers.roboflow.com/develop/learn/track/ "https://trackers.roboflow.com/develop/learn/track/"
[5]: https://supervision.roboflow.com/develop/how_to/count_in_zone/ "https://supervision.roboflow.com/develop/how_to/count_in_zone/"
[6]: https://blog.roboflow.com/monitor-retail-queues/ "https://blog.roboflow.com/monitor-retail-queues/"
[7]: https://supervision.roboflow.com/develop/how_to/track_objects/ "https://supervision.roboflow.com/develop/how_to/track_objects/"
[8]: https://supervision.roboflow.com/develop/how_to/save_detections/ "https://supervision.roboflow.com/develop/how_to/save_detections/"
