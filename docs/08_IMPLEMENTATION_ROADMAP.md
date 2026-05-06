# Implementation Roadmap

## 1. Mục tiêu roadmap

Roadmap này dùng để triển khai codebase mới theo hướng đồ án tốt nghiệp. Thứ tự ưu tiên là có demo end-to-end trước, sau đó tăng độ hoàn chỉnh về data quality, observability và evaluation.

## 2. Cấu trúc monorepo đề xuất

```text
retail-video-analytics/
├── pyproject.toml
├── uv.lock
├── .env.example
├── Makefile
├── docker/
│   ├── docker-compose.yml
│   ├── docker-compose.dev.yml
│   ├── vision/Dockerfile
│   ├── api/Dockerfile
│   └── streamlit/Dockerfile
├── configs/
│   ├── cameras.yaml
│   └── logging.yaml
├── packages/
│   ├── rva-core/
│   ├── rva-storage/
│   └── rva-messaging/
├── services/
│   ├── vision/
│   ├── flink-jobs/
│   ├── api/
│   └── streamlit/
├── infra/
│   ├── postgres/
│   ├── pulsar/
│   ├── flink/
│   ├── trino/
│   └── grafana/
├── scripts/
│   ├── setup_gcs.sh
│   ├── migrate_db.py
│   ├── generate_test_events.py
│   └── backfill_gold.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── data/
│   ├── videos/
│   └── models/
└── docs/
```

## 3. Shared packages

### `rva-core`

Nội dung:

- Pydantic models cho event contracts.
- Settings loader.
- Common constants.
- Time parsing utilities.
- Data quality validation helpers.

### `rva-storage`

Nội dung:

- Redis client.
- PostgreSQL async client.
- GCS client.
- Trino client.

### `rva-messaging`

Nội dung:

- Pulsar producer.
- Pulsar consumer helpers.
- Serialization/deserialization.
- Topic config.

## 4. Milestone 0: Repository foundation

Thời lượng: 1 đến 2 ngày.

Tasks:

- Tạo uv workspace.
- Tạo shared packages.
- Tạo `.env.example`.
- Tạo Docker Compose base.
- Tạo Makefile.
- Tạo logging config.

Output:

- `uv sync` chạy được.
- `make lint`, `make test` có skeleton.
- Docker Compose khởi động được Redis/PostgreSQL/Pulsar.

## 5. Milestone 1: Event contract and test data

Thời lượng: 2 đến 3 ngày.

Tasks:

- Implement Pydantic models:
  - `DetectionFrameEvent`
  - `DetectionObject`
  - `TrackLifecycleEvent`
  - `AlertEvent`
- Implement JSON schema export.
- Implement test event generator.
- Implement contract tests.

Output:

- Có thể generate detection events giả.
- Contract tests pass.
- Invalid events bị reject rõ ràng.

## 6. Milestone 2: Vision MVP

Thời lượng: 4 đến 7 ngày.

Tasks:

- Đọc video file bằng OpenCV.
- Chạy YOLO person detection.
- Tích hợp BoTSORT hoặc tracker tương đương.
- Build `DetectionFrameEvent`.
- Publish vào Pulsar.
- Sample frame và lưu GCS hoặc local adapter.
- Ghi track lifecycle vào PostgreSQL.

Output:

- Chạy `make run-vision`.
- Pulsar topic nhận event.
- PostgreSQL có track start/sample/end.
- Frame sample có URI.

## 7. Milestone 3: Streaming realtime path

Thời lượng: 5 đến 8 ngày.

Tasks:

- Flink source đọc Pulsar.
- Parse và validate event.
- Dedup theo `event_id`.
- Compute current count.
- Compute heatmap grid.
- Write Redis state.
- Generate density alerts.
- Write alerts vào PostgreSQL.

Output:

- Redis có live stats và heatmap.
- Alert tạo đúng khi vượt threshold.
- Flink UI hiển thị job health.
- Có test với generated events.

## 8. Milestone 4: Lakehouse path

Thời lượng: 5 đến 10 ngày.

Tasks:

- Configure Iceberg catalog trên GCS hoặc local warehouse.
- Write Bronze table.
- Build Silver detections table.
- Build Gold minute metrics.
- Build Gold hourly heatmap.
- Configure Trino connector.
- Viết SQL query mẫu.

Output:

- Trino query được Bronze/Silver/Gold.
- Grafana có datasource Trino.
- Có dữ liệu lịch sử cho dashboard.

## 9. Milestone 5: API serving

Thời lượng: 3 đến 5 ngày.

Tasks:

- FastAPI app skeleton.
- Health endpoints.
- Live stats endpoints.
- Heatmap endpoints.
- Alerts endpoints.
- Track search endpoints.
- GCS signed URL endpoint.
- Optional MJPEG stream endpoint.

Output:

- API trả dữ liệu từ Redis/PostgreSQL/Trino/GCS.
- Swagger/OpenAPI dùng được.
- Integration tests cho API chính.

## 10. Milestone 6: Dashboards

Thời lượng: 4 đến 7 ngày.

Tasks:

- Streamlit Live Monitor.
- Streamlit Alerts.
- Streamlit Track Replay.
- Streamlit Historical page.
- Grafana Retail KPI dashboard.
- Grafana Pipeline Health dashboard.

Output:

- Demo UI đầy đủ cho hội đồng.
- Live path và historical path đều có màn hình minh họa.

## 11. Milestone 7: Observability and reliability

Thời lượng: 3 đến 5 ngày.

Tasks:

- Prometheus metrics cho API/vision.
- Export Flink/Pulsar/Redis/PostgreSQL metrics.
- Add structured logging.
- Add DLQ view hoặc invalid event report.
- Test restart Flink/vision/API.

Output:

- Có dashboard health.
- Có số liệu latency, throughput, error rate.
- Có minh chứng recovery trong evaluation.

## 12. Milestone 8: Evaluation and report

Thời lượng: 5 đến 10 ngày.

Tasks:

- Chuẩn bị kịch bản benchmark.
- Chạy latency test.
- Chạy throughput test.
- Chạy data quality test.
- Chạy failure recovery test.
- Tổng hợp biểu đồ và bảng số liệu.
- Viết báo cáo kiến trúc và đánh giá.

Output:

- Bảng kết quả đánh giá.
- Hình ảnh dashboard.
- Luận giải trade-off.

## 13. MVP cut line

Nếu thời gian hạn chế, MVP tối thiểu cần:

1. Video file -> YOLO/tracking -> Pulsar.
2. Flink -> Redis live count/heatmap.
3. Flink hoặc script -> Iceberg Bronze/Silver/Gold tối thiểu.
4. FastAPI -> Streamlit live monitor.
5. Trino/Grafana historical chart.
6. Một kịch bản evaluation latency và data quality.

Có thể hoãn:

- Multi-camera process manager đầy đủ.
- GCS thật, thay bằng local object storage adapter nếu cần.
- Advanced alert logic.
- Track replay đẹp.
- Production authentication.

## 14. Rủi ro và giảm thiểu

| Rủi ro | Tác động | Giảm thiểu |
|---|---|---|
| GPU không đủ | Vision chậm | Dùng YOLO11n, giảm FPS, dùng video file ngắn |
| Flink/Iceberg cấu hình lâu | Chậm roadmap | MVP dùng local warehouse trước |
| Streamlit video không mượt | UI kém | Dùng latest frame polling hoặc MJPEG |
| GCS credentials phức tạp | Block demo | Tạo local storage adapter có cùng interface |
| Dữ liệu detection nhiễu | Metric sai | Thêm threshold và data quality report |
| Quá nhiều công nghệ | Khó hoàn thành | Giữ MVP nhỏ, phần production nêu trong docs |

## 15. Definition of done

Một milestone chỉ được coi là xong khi có:

- Code chạy được.
- Config/env mẫu.
- Test tối thiểu.
- Log hoặc metric quan sát được.
- Tài liệu ngắn trong README hoặc docs.

