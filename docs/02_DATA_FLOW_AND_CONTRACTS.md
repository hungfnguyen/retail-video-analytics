# Data Flow And Contracts

## 1. Mục tiêu

Tài liệu này định nghĩa cách dữ liệu đi qua hệ thống và contract giữa các service. Contract rõ ràng giúp pipeline dễ kiểm thử, dễ replay, dễ evolve schema và giảm lỗi khi nhiều module phát triển độc lập.

## 2. Data flow tổng thể

```text
Camera / Video
    |
    v
Vision Edge Service
    |
    +--> DetectionFrameEvent -> Pulsar topic detection_frames
    |
    +--> Sampled frame jpg -> S3
    |
    +--> TrackLifecycleEvent -> PostgreSQL hoặc Pulsar topic track_lifecycle
    |
    v
Flink
    |
    +--> Realtime aggregates -> Redis
    +--> AlertEvent -> PostgreSQL + Redis pub/sub
    +--> Bronze/Silver/Gold tables -> Iceberg
```

## 3. Time semantics

Hệ thống dùng ba loại thời gian:

| Trường | Ý nghĩa | Nguồn |
|---|---|---|
| `capture_ts` | Thời điểm frame được camera/video reader lấy ra | Vision service |
| `event_ts` | Thời điểm nghiệp vụ dùng cho windowing | Thường bằng `capture_ts` |
| `ingest_ts` | Thời điểm event được publish hoặc nhận vào pipeline | Producer/Flink |
| `process_ts` | Thời điểm Flink xử lý event | Flink runtime |

Quy tắc:

- Window analytics dùng `event_ts`.
- Latency đo bằng `process_ts - capture_ts`.
- Lakehouse partition ưu tiên theo `event_date` lấy từ `event_ts`.
- Nếu `event_ts` thiếu hoặc sai format, event vào dead-letter topic.

## 4. Topic naming

| Topic | Nội dung | Partition key |
|---|---|---|
| `persistent://retail/ingest/detection-frames-v1` | Detection frame events từ vision | `store_id:camera_id` |
| `persistent://retail/ops/track-lifecycle-v1` | Track start/end/sample nếu publish qua broker | `store_id:camera_id:track_id` |
| `persistent://retail/ops/alerts-v1` | Alert events | `store_id:camera_id` |
| `persistent://retail/ops/system-metrics-v1` | FPS, lag, worker health | `service_id` |
| `persistent://retail/metadata/dlq-events` | Event lỗi schema hoặc quality rule | `source_topic` |

Trong MVP có thể chỉ dùng topic detection frame và để Flink sinh ra alert/metrics.

## 5. DetectionFrameEvent contract

Một message tương ứng một frame đã xử lý.

```json
{
  "schema_version": "1.0",
  "event_id": "cam_01-000001502-2026-05-05T10:30:00.123Z",
  "pipeline_run_id": "run_20260505_103000",
  "store_id": "store_001",
  "camera_id": "cam_01",
  "frame_index": 1502,
  "capture_ts": "2026-05-05T10:30:00.123Z",
  "ingest_ts": "2026-05-05T10:30:00.180Z",
  "image_size": {
    "width": 1920,
    "height": 1080
  },
  "model": {
    "name": "yolo11n",
    "version": "0.1",
    "confidence_threshold": 0.4,
    "tracker": "botsort"
  },
  "frame_ref": {
    "saved": true,
    "uri": "s3://retail-video-analytics/frames/2026-05-05/cam_01/10/10-30-00_001502.jpg"
  },
  "detections": [
    {
      "track_id": 42,
      "class_id": 0,
      "class_name": "person",
      "confidence": 0.87,
      "bbox": {
        "x1": 100,
        "y1": 200,
        "x2": 300,
        "y2": 620
      },
      "centroid": {
        "x": 200,
        "y": 410
      }
    }
  ]
}
```

## 6. Required fields

| Field | Bắt buộc | Ghi chú |
|---|---|---|
| `schema_version` | Có | Major/minor version |
| `event_id` | Có | Dùng cho dedup |
| `pipeline_run_id` | Có | Dùng lineage và replay |
| `store_id` | Có | Scope theo cửa hàng |
| `camera_id` | Có | Scope theo camera |
| `frame_index` | Có | Tăng dần trong một run |
| `capture_ts` | Có | ISO-8601 UTC |
| `image_size.width` | Có | Pixel width |
| `image_size.height` | Có | Pixel height |
| `detections` | Có | Có thể là mảng rỗng |

## 7. DetectionObject contract

| Field | Type | Rule |
|---|---|---|
| `track_id` | integer hoặc null | Null nếu detector chưa tracking được |
| `class_id` | integer | Với person thường là `0` |
| `class_name` | string | MVP chỉ xử lý `person` |
| `confidence` | float | 0.0 đến 1.0 |
| `bbox.x1` | integer | 0 đến width - 1 |
| `bbox.y1` | integer | 0 đến height - 1 |
| `bbox.x2` | integer | Lớn hơn `x1` |
| `bbox.y2` | integer | Lớn hơn `y1` |
| `centroid.x` | integer | Nằm trong bbox |
| `centroid.y` | integer | Nằm trong bbox |

## 8. TrackLifecycleEvent contract

Track lifecycle có thể được ghi trực tiếp vào PostgreSQL bởi vision service hoặc publish qua Pulsar để Flink xử lý. Với MVP, ghi PostgreSQL trực tiếp đơn giản hơn. Với kiến trúc data platform đầy đủ, publish qua Pulsar giúp replay và audit tốt hơn.

```json
{
  "schema_version": "1.0",
  "event_id": "track-cam_01-42-start-2026-05-05T10:30:00.123Z",
  "store_id": "store_001",
  "camera_id": "cam_01",
  "track_id": 42,
  "event_type": "track_start",
  "event_ts": "2026-05-05T10:30:00.123Z",
  "position": {
    "x": 200,
    "y": 410
  },
  "frame_uri": "s3://retail-video-analytics/frames/2026-05-05/cam_01/10/10-30-00_001502.jpg"
}
```

Allowed `event_type`:

- `track_start`
- `position_sample`
- `track_end`

## 9. AlertEvent contract

```json
{
  "schema_version": "1.0",
  "alert_id": "alert-cam_01-20260505T103005Z-density",
  "alert_type": "density_spike",
  "severity": "medium",
  "store_id": "store_001",
  "camera_id": "cam_01",
  "event_ts": "2026-05-05T10:30:05Z",
  "window": {
    "start_ts": "2026-05-05T10:30:00Z",
    "end_ts": "2026-05-05T10:30:05Z"
  },
  "metrics": {
    "person_count": 28,
    "threshold": 20,
    "max_heatmap_value": 15.5
  },
  "hotspot": {
    "grid_x": 32,
    "grid_y": 18
  },
  "status": "active"
}
```

## 10. Idempotency

Mỗi event phải có khóa idempotency.

| Event | Idempotency key |
|---|---|
| Detection frame | `event_id` |
| Detection object trong Silver | `event_id + detection_index` hoặc hash bbox/track |
| Track lifecycle | `camera_id + track_id + event_type + event_ts` |
| Alert | `camera_id + alert_type + window_start + window_end` |
| Heatmap cell aggregate | `camera_id + window_start + grid_x + grid_y` |

Redis và PostgreSQL sinks cần thiết kế để duplicate không tạo kết quả sai nghiêm trọng:

- PostgreSQL dùng unique constraint.
- Redis current count dùng `SET`, không dùng cộng dồn nếu event có thể replay.
- Redis heatmap live có TTL và window ngắn để duplicate tự hết ảnh hưởng.
- Gold tables dùng upsert/merge theo aggregate key nếu batch rewrite.

## 11. Data quality rules

### Schema rules

- `schema_version` phải thuộc danh sách version hỗ trợ.
- `camera_id`, `store_id`, `event_id` không rỗng.
- `capture_ts` parse được ISO-8601.
- `image_size.width` và `image_size.height` lớn hơn 0.
- `detections` là array.

### Business rules

- Chỉ nhận `class_name = person` cho các metric người.
- `confidence >= confidence_threshold` mới vào Silver.
- `bbox` phải nằm trong frame hoặc được clip vào biên frame.
- `track_id` chỉ được coi unique trong phạm vi camera và session.
- Event quá trễ so với watermark được đưa vào late-event side output.

### Quality outputs

| Output | Ý nghĩa |
|---|---|
| `valid_record_count` | Số event hợp lệ |
| `invalid_record_count` | Số event lỗi schema |
| `late_record_count` | Số event trễ watermark |
| `duplicate_record_count` | Số event trùng id |
| `empty_detection_frame_count` | Frame không có detection |

## 12. Schema evolution

Quy tắc versioning:

- Thêm field optional: tăng minor version, ví dụ `1.0` -> `1.1`.
- Đổi type hoặc đổi ý nghĩa field: tăng major version, ví dụ `1.x` -> `2.0`.
- Không xóa field đang có consumer dùng trong cùng major version.
- Consumer phải bỏ qua field lạ.
- Lakehouse Bronze lưu raw payload để có thể parse lại khi schema thay đổi.

## 13. Privacy and security

- Không lưu thông tin định danh cá nhân.
- Không dùng face recognition.
- Sampled frame có lifecycle retention ngắn.
- RTSP URL và S3 credentials không commit vào repo.
- Dashboard chỉ hiển thị track ID kỹ thuật, không hiển thị danh tính người.

## 14. Contract testing

Mỗi contract cần test:

- JSON schema validation.
- Backward compatibility giữa producer và consumer.
- Invalid bbox.
- Empty detections.
- Missing optional `frame_ref`.
- Duplicate `event_id`.
- Late event theo watermark.

