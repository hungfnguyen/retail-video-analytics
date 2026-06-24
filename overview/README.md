# Overview — Mô Tả Dự Án (Luận Văn Tốt Nghiệp)

Thư mục này chứa tài liệu mô tả toàn bộ hệ thống **Retail Video Analytics** phục vụ luận văn tốt nghiệp chuyên ngành Data Engineering.

## Danh sách tài liệu

| File | Nội dung |
|---|---|
| [00_system_overview.md](00_system_overview.md) | Giới thiệu đề tài, công nghệ sử dụng, kết quả tổng quan |
| [01_architecture.md](01_architecture.md) | Kiến trúc dual-path, luồng dữ liệu đầy đủ, Medallion design |
| [02_vision_service.md](02_vision_service.md) | Edge processing: YOLO11, ByteTrack, zone detection, alert clip |
| [03_flink_pipeline.md](03_flink_pipeline.md) | 9 Flink jobs, Bronze→Silver→Gold→Serving pipeline |
| [04_serving_layer.md](04_serving_layer.md) | FastAPI endpoints, alert evaluator, React dashboard |
| [05_data_schema.md](05_data_schema.md) | Schema đầy đủ: Iceberg tables, Redis keys, Pulsar topics, S3 |
| [06_deployment.md](06_deployment.md) | Docker Compose, env vars, Vision config, cách khởi động |
| [07_thesis_evaluation.md](07_thesis_evaluation.md) | Kết quả đo đạc thực tế, hiệu năng, hạn chế |

## Tóm tắt hệ thống (1 trang)

```
Camera/Video → Vision (YOLO11 + ByteTrack) → Apache Pulsar
                                                    │
                              ┌─────────────────────┤
                              │                     │
                   Flink Lakehouse Jobs    Flink Realtime Job
                   (Bronze→Silver→Gold)   (Redis live state)
                              │                     │
                   Iceberg on S3          Redis
                   (Trino queryable)      (Live dashboard)
                              │                     │
                         Airflow                    │
                    (DAG-based refresh)             │
                              │                     │
                         Gold Serving ──────────────┤
                         Iceberg tables             │
                              └──────────┬──────────┘
                                      FastAPI
                                         │
                                   React Dashboard
                                (Live + Analytics + Heatmap)
```

**Stack:** Python · Java · YOLO11 · ByteTrack · Pulsar · Flink · Iceberg · S3 · Trino · Redis · Airflow · FastAPI · React · Docker · Nginx · AWS EC2
