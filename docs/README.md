# Retail Video Analytics - Thesis Documentation

## Mục tiêu

Retail Video Analytics là đồ án tốt nghiệp theo hướng Data Engineering: xây dựng hệ thống thu nhận, xử lý, lưu trữ và phục vụ dữ liệu sinh ra từ camera siêu thị. Trọng tâm của đồ án không chỉ là nhận diện người bằng Computer Vision, mà là thiết kế một data platform có streaming, lakehouse, schema contract, realtime serving, batch analytics, monitoring và kế hoạch đánh giá rõ ràng.

Thiết kế mới dùng hướng **metadata-first**:

- Video frame chỉ được lưu mẫu để tra cứu và minh họa.
- Dữ liệu chính của hệ thống là event metadata: camera, timestamp, track, bbox, confidence, heatmap cell.
- Realtime path phục vụ live heatmap và cảnh báo.
- Lakehouse path phục vụ phân tích lịch sử, báo cáo và truy vấn SQL.

## Bộ tài liệu

| File | Vai trò |
|---|---|
| [00_THESIS_SCOPE.md](./00_THESIS_SCOPE.md) | Phạm vi đồ án, mục tiêu, câu hỏi nghiên cứu, tiêu chí thành công |
| [01_TARGET_ARCHITECTURE.md](./01_TARGET_ARCHITECTURE.md) | Kiến trúc đích, các layer, công nghệ và luồng tổng thể |
| [02_DATA_FLOW_AND_CONTRACTS.md](./02_DATA_FLOW_AND_CONTRACTS.md) | Data flow, event schema, topic contract, idempotency, data quality |
| [03_STREAMING_PIPELINE.md](./03_STREAMING_PIPELINE.md) | Thiết kế Flink streaming jobs, watermark, window, state, alerting |
| [04_LAKEHOUSE_DESIGN.md](./04_LAKEHOUSE_DESIGN.md) | Thiết kế Iceberg lakehouse theo Bronze, Silver, Gold |
| [05_OPERATIONAL_STORAGE.md](./05_OPERATIONAL_STORAGE.md) | PostgreSQL, Redis, S3 và access pattern cho serving |
| [06_CAMERA_EDGE_PROCESSING.md](./06_CAMERA_EDGE_PROCESSING.md) | Xử lý camera tại edge: RTSP, YOLO, tracking, worker, publisher |
| [07_DASHBOARD_AND_SERVING.md](./07_DASHBOARD_AND_SERVING.md) | FastAPI, Streamlit, Grafana, API và dashboard requirements |
| [08_IMPLEMENTATION_ROADMAP.md](./08_IMPLEMENTATION_ROADMAP.md) | Roadmap triển khai codebase mới theo milestone |
| [09_EVALUATION_PLAN.md](./09_EVALUATION_PLAN.md) | Kế hoạch đánh giá chức năng, hiệu năng, chất lượng dữ liệu |
| [10_S3_INFRASTRUCTURE.md](./10_S3_INFRASTRUCTURE.md) | Thiết kế S3 bucket, folder structure, Iceberg namespace, partitioning, access control |

## Kiến trúc tóm tắt

```text
Camera / Video File
    |
    v
Vision Edge Service
RTSPReader -> YOLO11 -> BoTSORT -> Detection Publisher
    |
    +--> Pulsar: detection frame events
    +--> S3: sampled frames
    +--> PostgreSQL: track lifecycle metadata
    |
    v
Apache Flink
    |
    +--> Fast path: Redis + PostgreSQL alerts + FastAPI WebSocket
    |
    +--> Lakehouse path: Iceberg Bronze -> Silver -> Gold on S3
                                  |
                                  v
                                Trino
                                  |
                                  v
                      Grafana / Streamlit / SQL analysis
```

## Công nghệ chính

| Layer | Công nghệ | Mục đích |
|---|---|---|
| Vision edge | Python, OpenCV, YOLO11, BoTSORT | Đọc camera, detect person, tracking |
| Messaging | Apache Pulsar | Message bus cho detection events |
| Streaming | Apache Flink | Realtime metrics, alerting, ETL streaming |
| Realtime state | Redis | Live heatmap, current count, active tracks |
| Operational DB | PostgreSQL | Camera config, track lifecycle, alerts |
| Object storage | AWS S3 | Sampled frames, Iceberg table data |
| Lakehouse | Apache Iceberg | Bronze, Silver, Gold analytical tables |
| Query | Trino | SQL engine cho Iceberg |
| Serving | FastAPI, Streamlit, Grafana | API, live UI, historical dashboard |
| Observability | Prometheus, Grafana | System metrics và pipeline health |

## Nguyên tắc thiết kế

1. **Data Engineering first**: mọi module phải tạo ra dữ liệu có schema, lineage, timestamp và khả năng replay.
2. **Metadata-first**: không xử lý video như dữ liệu analytics chính; chỉ lưu sampled frames để tra cứu.
3. **Dual path**: realtime path tối ưu latency, lakehouse path tối ưu tính đúng và phân tích lịch sử.
4. **Heatmap-first, no fixed zones**: mật độ được tính từ tọa độ bbox/centroid trên toàn frame, không phụ thuộc vùng vẽ tay.
5. **Operational storage tách khỏi analytical storage**: Redis/PostgreSQL phục vụ ứng dụng, Iceberg/Trino phục vụ phân tích.
6. **MVP có thể chạy local**: demo đồ án phải chạy được với video file, Docker Compose và dữ liệu giả lập nếu không có camera thật.

## Cổng dịch vụ đề xuất

| Service | Port | Vai trò |
|---|---:|---|
| FastAPI | 8000 | REST API, WebSocket, MJPEG endpoint |
| Streamlit | 8501 | Live monitor, event search, track replay |
| Grafana | 3000 | Historical KPI và system dashboard |
| Flink UI | 8081 | Theo dõi streaming jobs |
| Pulsar Admin | 8080 hoặc 8084 | Theo dõi broker và topic |
| Trino | 8083 | SQL query engine |
| Redis | 6379 | Realtime state |
| PostgreSQL | 5432 | Operational metadata |
