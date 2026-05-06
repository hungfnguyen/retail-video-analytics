# Target Architecture

## 1. Mục tiêu kiến trúc

Kiến trúc đích cần chứng minh rằng hệ thống xử lý video camera siêu thị có thể được thiết kế như một data platform hoàn chỉnh. Computer Vision chỉ là bước tạo dữ liệu đầu vào; phần chính của đồ án là ingestion, stream processing, storage, serving, quality và monitoring.

Mục tiêu:

- Chạy được end-to-end từ camera/video đến dashboard.
- Tách realtime path và analytical path.
- Có data contract rõ ràng giữa các service.
- Có khả năng replay và backfill dữ liệu lịch sử.
- Có monitoring để đánh giá health và performance.
- Có cấu trúc codebase mới đủ rõ để phát triển tiếp.

## 2. Kiến trúc tổng thể

```text
                         +----------------------+
                         | Camera / Video Files |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         | Vision Edge Service  |
                         | RTSP -> YOLO -> MOT  |
                         +----+------------+----+
                              |            |
                              |            +------------------+
                              |                               |
                              v                               v
                 +------------------------+        +----------------------+
                 | Apache Pulsar          |        | GCS sampled frames   |
                 | detection frame events |        | jpg, 1 fps optional  |
                 +-----------+------------+        +----------+-----------+
                             |                                |
                             v                                |
               +-------------+----------------+               |
               | Apache Flink Streaming Jobs  |               |
               +-------------+----------------+               |
                             |                                |
                 +-----------+------------+                   |
                 |                        |                   |
                 v                        v                   |
        +----------------+       +--------------------+        |
        | Fast Path      |       | Lakehouse Path     |        |
        | Redis, Alerts  |       | Iceberg B/S/G      |        |
        +-------+--------+       +---------+----------+        |
                |                          |                   |
                v                          v                   |
        +----------------+       +--------------------+        |
        | FastAPI        |       | Trino SQL Engine   |<-------+
        | REST, WS, MJPEG|       +---------+----------+
        +-------+--------+                 |
                |                          |
                v                          v
        +----------------+       +--------------------+
        | Streamlit      |       | Grafana            |
        | Live monitor   |       | KPI, history, ops  |
        +----------------+       +--------------------+
```

## 3. Các layer chính

| Layer | Thành phần | Trách nhiệm |
|---|---|---|
| Edge processing | Vision service | Đọc camera/video, detect, tracking, publish event |
| Messaging | Pulsar | Buffer event stream, decouple producer và consumer |
| Stream processing | Flink | Validation, dedup, window aggregate, alert, lakehouse write |
| Realtime serving | Redis | Live heatmap, current count, active track state |
| Operational storage | PostgreSQL | Camera config, track lifecycle, alert history |
| Object storage | GCS | Sampled frames, Iceberg table files |
| Lakehouse | Iceberg | Bronze, Silver, Gold analytical tables |
| Query | Trino | SQL query cho dashboard và analyst |
| Application | FastAPI, Streamlit | API, live dashboard, event investigation |
| Observability | Prometheus, Grafana | Metrics, logs, health, lag |

## 4. Dual-path design

### Fast path

Fast path phục vụ các yêu cầu cần độ trễ thấp:

- Live person count theo camera.
- Live heatmap overlay.
- Active tracks.
- Density spike alert.
- Camera status.

Luồng:

```text
Pulsar -> Flink realtime job -> Redis/PostgreSQL -> FastAPI -> Streamlit
```

Đặc điểm:

- Ưu tiên latency.
- State được giữ trong Flink và Redis.
- Redis sink có thể at-least-once, cần key/idempotency để giảm tác động duplicate.
- Không dùng cho phân tích lịch sử dài hạn.

### Lakehouse path

Lakehouse path phục vụ phân tích dữ liệu lịch sử:

- Traffic theo phút, giờ, ngày.
- Peak count.
- Unique tracks.
- Historical heatmap.
- So sánh giữa các camera hoặc ngày.

Luồng:

```text
Pulsar -> Flink -> Iceberg Bronze -> Silver -> Gold -> Trino -> Grafana
```

Đặc điểm:

- Ưu tiên tính đầy đủ, khả năng query và schema evolution.
- Latency có thể từ vài chục giây đến vài phút tùy checkpoint và compaction.
- Hỗ trợ replay/backfill.

## 5. Technology stack đề xuất

| Nhóm | Công nghệ | Lý do chọn |
|---|---|---|
| Model inference | YOLO11, Ultralytics | Dễ triển khai, đủ tốt cho demo person detection |
| Tracking | BoTSORT | Có track ID, phục vụ lifecycle và unique count |
| Message broker | Apache Pulsar | Topic-based event ingestion, schema, multi-tenant friendly |
| Stream processing | Apache Flink | Event time, watermark, stateful window, CEP/alerting |
| Realtime state | Redis | Latency thấp, data structure phù hợp heatmap và counter |
| Operational DB | PostgreSQL | ACID, JSONB, partitioning, query metadata tốt |
| Lakehouse table | Apache Iceberg | Schema evolution, hidden partitioning, Trino support |
| Object storage | GCS | Managed object storage, phù hợp frame và Iceberg files |
| Query engine | Trino | Interactive SQL trên Iceberg |
| API | FastAPI | Python async, REST, WebSocket, MJPEG endpoint |
| Dashboard | Streamlit, Grafana | Streamlit cho live investigation, Grafana cho KPI/ops |
| Packaging | uv workspace | Quản lý Python monorepo rõ ràng |
| Deployment demo | Docker Compose | Dễ chạy trên máy demo hoặc VM |

## 6. Dữ liệu chính của hệ thống

Hệ thống không lấy video raw làm dữ liệu phân tích chính. Dữ liệu chính là event metadata:

- `DetectionFrameEvent`: một frame đã được xử lý, gồm danh sách detections.
- `DetectionObject`: một object/person trong frame.
- `TrackLifecycleEvent`: track start, position sample, track end.
- `HeatmapMetric`: mật độ theo grid cell.
- `AlertEvent`: cảnh báo mật độ hoặc camera health.
- `SystemMetric`: FPS, lag, error, checkpoint duration.

## 7. Nguyên tắc heatmap-first

Thiết kế không phụ thuộc fixed zones vẽ tay. Mật độ được tính bằng cách ánh xạ centroid của bbox vào grid:

```text
grid_x = floor(center_x / frame_width  * grid_width)
grid_y = floor(center_y / frame_height * grid_height)
```

Lợi ích:

- Không cần cấu hình zone cho mỗi camera trong MVP.
- Lưu được thông tin không gian đầy đủ hơn count theo zone.
- Có thể suy ra hotspot về sau.
- Dễ so sánh heatmap giữa realtime và historical path.

## 8. Deployment mode

### Local thesis demo

- Video file thay cho camera RTSP.
- Docker Compose chạy Pulsar, Flink, Redis, PostgreSQL, Trino, Grafana, API, Streamlit.
- GCS có thể thay bằng bucket thật hoặc adapter local trong môi trường dev.
- Một đến hai camera/video stream.

### Single VM demo

- Một VM có GPU, ví dụ NVIDIA T4.
- Vision service chạy với GPU.
- Hạ tầng data chạy cùng VM bằng Docker Compose.
- Phù hợp demo tốt nghiệp.

### Production direction

- Edge VM tại từng store xử lý camera.
- Pulsar/Flink/Lakehouse tập trung.
- GCS dùng bucket chung có prefix theo store.
- Redis/PostgreSQL có HA hoặc managed service.

## 9. Quyết định kiến trúc quan trọng

| Quyết định | Lý do |
|---|---|
| Tách fast path và lakehouse path | Realtime và analytics có yêu cầu latency/consistency khác nhau |
| Không lưu raw 30 FPS vào PostgreSQL | PostgreSQL không phù hợp làm kho raw detection tốc độ cao |
| Dùng Iceberg cho lịch sử | Cần schema evolution, partition, SQL analytics |
| Dùng Redis cho live state | Heatmap, count, active tracks cần latency thấp |
| Dùng sampled frames | Cần minh họa event nhưng tránh chi phí lưu video lớn |
| Track ID scoped theo camera | Tracker không đảm bảo global identity |
| Event contract versioned | Cho phép đổi schema mà không phá consumer |

## 10. Ranh giới giữa các service

| Service | Input | Output |
|---|---|---|
| Vision | RTSP/video file | Pulsar events, sampled frames, optional track lifecycle |
| Flink realtime | Pulsar events | Redis state, alerts, metrics |
| Flink lakehouse | Pulsar events | Iceberg Bronze/Silver/Gold |
| API | Redis, PostgreSQL, GCS, Trino | REST, WebSocket, MJPEG |
| Streamlit | API | Live UI, event search, replay |
| Grafana | Trino, Prometheus | KPI và system dashboards |

## 11. Constraints

- Demo phải chấp nhận được khi không có camera thật.
- Latency Streamlit phụ thuộc cơ chế polling, vì vậy live video mượt nên đi qua MJPEG hoặc WebRTC endpoint.
- Exactly-once end-to-end khó đạt khi có Redis và external API sink. Thiết kế thực tế là exactly-once/transactional ở lakehouse path và at-least-once có idempotency ở serving path.
- Computer Vision accuracy không phải tiêu chí duy nhất; pipeline correctness và data quality quan trọng ngang bằng trong đồ án Data Engineering.
