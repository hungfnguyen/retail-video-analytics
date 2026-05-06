# Evaluation Plan

## 1. Mục tiêu đánh giá

Đồ án Data Engineering cần đánh giá nhiều hơn việc model detect đúng hay sai. Kế hoạch đánh giá tập trung vào:

- Functional correctness.
- Streaming latency.
- Throughput.
- Data quality.
- Storage/query performance.
- Reliability và recovery.
- Resource usage.

## 2. Câu hỏi đánh giá

| ID | Câu hỏi |
|---|---|
| E1 | Pipeline có chạy end-to-end từ video đến dashboard không? |
| E2 | Realtime path cập nhật live metrics trong bao lâu? |
| E3 | Hệ thống xử lý được bao nhiêu frame/event mỗi giây? |
| E4 | Bao nhiêu event bị invalid, late hoặc duplicate? |
| E5 | Lakehouse query historical metrics có đủ nhanh cho dashboard không? |
| E6 | Khi service lỗi, hệ thống phục hồi như thế nào? |
| E7 | Tài nguyên CPU/RAM/GPU có phù hợp với quy mô demo không? |

## 3. Dataset và kịch bản demo

### Input sources

| Source | Mục đích |
|---|---|
| Video siêu thị mẫu | Demo chính |
| Video đông người | Test alert và heatmap |
| Video ít người | Baseline |
| Generated events | Test streaming/lakehouse không phụ thuộc model |
| Invalid generated events | Test data quality |

### Kịch bản

1. Một camera/video chạy 5 phút.
2. Hai camera/video chạy song song nếu đủ tài nguyên.
3. Replay generated events với tốc độ cao.
4. Inject invalid events.
5. Restart Flink hoặc API trong lúc chạy.

## 4. Functional evaluation

| Test | Expected result |
|---|---|
| Vision publish event | Pulsar topic nhận `DetectionFrameEvent` |
| Frame sampling | GCS/local storage có frame mỗi 1 giây |
| Track lifecycle | PostgreSQL có start/sample/end |
| Realtime count | Redis `stats:count` cập nhật |
| Heatmap | Redis `heatmap:live` có cells |
| Alert | Alert sinh khi vượt threshold |
| Bronze write | Iceberg Bronze có frame events |
| Silver write | Iceberg Silver có detections |
| Gold write | Gold có minute/hour aggregates |
| Dashboard | Streamlit/Grafana hiển thị dữ liệu |

## 5. Latency metrics

### Metrics

| Metric | Công thức |
|---|---|
| Producer latency | `ingest_ts - capture_ts` |
| Flink processing latency | `flink_process_ts - ingest_ts` |
| Realtime serving latency | `dashboard_seen_ts - capture_ts` |
| Alert latency | `alert_created_ts - window_end_ts` |
| Lakehouse availability latency | `trino_query_seen_ts - capture_ts` |

### Target cho demo

| Path | Target |
|---|---:|
| Vision to Pulsar | < 500 ms |
| Pulsar to Redis | < 2 giây |
| Alert visible on UI | < 5 giây |
| Bronze availability | < 2 phút |
| Gold availability | < 5 phút |

Các target này dành cho demo tốt nghiệp, không phải SLA production.

## 6. Throughput evaluation

### Metrics

| Metric | Đơn vị |
|---|---|
| Processed FPS per camera | frames/second |
| Pulsar publish rate | messages/second |
| Flink input rate | records/second |
| Flink output rate | records/second |
| Redis write rate | ops/second |
| Iceberg write rate | records/second |

### Test plan

1. Chạy 1 video trong 5 phút, đo FPS trung bình.
2. Chạy generated events ở 1x, 2x, 5x tốc độ video.
3. Nếu có tài nguyên, chạy 2 đến 4 camera giả lập.
4. Ghi nhận CPU/RAM/GPU và lag.

## 7. Data quality evaluation

### Quality dimensions

| Dimension | Metric |
|---|---|
| Completeness | Tỷ lệ event có đủ required fields |
| Validity | Tỷ lệ bbox/timestamp/confidence hợp lệ |
| Uniqueness | Duplicate `event_id` rate |
| Timeliness | Late event rate |
| Consistency | Count giữa Bronze, Silver, Gold có khớp không |
| Accuracy signal | Confidence distribution, empty frame ratio |

### Test cases

- Event thiếu `camera_id`.
- Event timestamp sai format.
- Event bbox ngoài frame.
- Event duplicate `event_id`.
- Event capture_ts trễ hơn watermark.
- Frame không có detection.

Expected:

- Invalid events không làm job crash.
- DLQ hoặc quality report ghi nhận số lượng lỗi.
- Silver chỉ chứa record hợp lệ.

## 8. Lakehouse query evaluation

### Queries cần benchmark

1. Traffic theo giờ cho một ngày.
2. Top camera theo peak count trong 7 ngày.
3. Historical heatmap theo camera và ngày.
4. Daily store summary.
5. Data quality summary theo ngày.

### Metrics

| Metric | Ghi chú |
|---|---|
| Query duration | Từ Trino |
| Scanned data size | Nếu lấy được từ Trino |
| Number of files | Kiểm tra small files |
| Partition pruning | Query có filter `event_date`, `store_id`, `camera_id` |

Target demo:

- Query Gold tables dưới 5 giây với dataset demo.
- Query Bronze có thể chậm hơn nhưng vẫn giải thích được.

## 9. Reliability evaluation

| Scenario | Cách test | Expected |
|---|---|---|
| Vision worker crash | Kill process | CameraManager restart |
| API restart | Restart container | Dashboard reconnect được |
| Redis restart | Restart Redis | Live state mất tạm thời nhưng pipeline không mất lakehouse data |
| Flink restart | Restart job | Resume từ checkpoint |
| Invalid events burst | Publish nhiều event lỗi | Job không crash, DLQ tăng |
| Camera disconnect | Dừng video/RTSP | Camera offline alert |

## 10. Resource evaluation

Ghi nhận:

- CPU usage.
- RAM usage.
- GPU utilization.
- GPU memory.
- Disk usage.
- Network I/O.
- Redis memory.
- PostgreSQL table size.
- Iceberg data size.

Tool:

- `docker stats`
- `nvidia-smi`
- Prometheus/Grafana
- Flink UI
- Pulsar metrics
- PostgreSQL stats

## 11. Computer Vision evaluation scope

CV không phải trọng tâm duy nhất, nhưng vẫn cần đánh giá cơ bản:

| Metric | Cách làm |
|---|---|
| Detection sanity | Kiểm tra sample frames có bbox hợp lý |
| Confidence distribution | Histogram confidence trong Silver |
| Tracking stability | Số lần track fragment bất thường |
| FPS impact | So sánh YOLO11n vs YOLO11s nếu có |

Nếu không có labeled dataset, không nên tuyên bố mAP chính xác. Báo cáo nên nói rõ đây là evaluation mức pipeline/demo, không phải benchmark model CV chuẩn.

## 12. Báo cáo kết quả

Nên có các bảng:

### Latency summary

| Path | p50 | p95 | max | Ghi chú |
|---|---:|---:|---:|---|
| Vision -> Pulsar | | | | |
| Pulsar -> Redis | | | | |
| Alert -> UI | | | | |
| Pulsar -> Bronze | | | | |
| Silver -> Gold | | | | |

### Throughput summary

| Scenario | FPS | Pulsar msg/s | Flink records/s | CPU | GPU |
|---|---:|---:|---:|---:|---:|
| 1 camera | | | | | |
| 2 cameras | | | | | |
| Generated 5x | | | | | |

### Data quality summary

| Scenario | Input | Valid | Invalid | Duplicate | Late |
|---|---:|---:|---:|---:|---:|
| Normal video | | | | | |
| Invalid injected | | | | | |

## 13. Success criteria

Đồ án được xem là đạt nếu:

- End-to-end demo chạy được.
- Có số liệu latency và throughput.
- Có bảng Bronze/Silver/Gold truy vấn được.
- Có live dashboard và historical dashboard.
- Có data quality handling.
- Có ít nhất một test recovery hoặc restart.
- Báo cáo giải thích rõ trade-off giữa fast path và lakehouse path.

