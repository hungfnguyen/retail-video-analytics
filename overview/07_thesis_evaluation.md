# Đánh Giá Luận Văn — Kết Quả Thực Nghiệm

## 1. Tiêu chí đánh giá (theo docs/00_THESIS_SCOPE.md)

| Tiêu chí | Kết quả |
|---|---|
| Vision produces detection events | ✅ 2 cameras, ~25fps, YOLO11l + ByteTrack |
| Pulsar receives metadata events | ✅ Topic `events` nhận events từ cam_01, cam_02 |
| Redis has current count + tracks | ✅ `stats:count`, `track:active`, `heatmap:live` |
| Iceberg Bronze/Silver/Gold tables | ✅ 9 tables trong `lakehouse.rva` |
| Trino can query all tables | ✅ Trino 468 query được qua catalog REST |
| FastAPI returns live + analytics | ✅ `/live/{cam}/dashboard` + `/analytics/dashboard` |
| React frontend displays realtime | ✅ Live Monitor với MJPEG stream, alerts, zones |
| S3 contains Iceberg warehouse | ✅ `s3://s3-retail-video-analytics/lakehouse/` |

## 2. Kết quả đo đạc thực tế (2026-06-23)

### Dữ liệu lakehouse (1 ngày hoạt động — 2026-06-21)

| Bảng | Số rows | Ghi chú |
|---|---|---|
| `bronze_raw` | ~72.000 events | ~1 event/frame, 2 cameras × ~36.000 frames |
| `silver_detections_v2` | ~363.000 rows | 1 row/detection/frame |
| `gold_track_summary_v2` | ~5.816 tracks | Unique persons (dwell-based) |
| `gold_queue_sessions` | ~240 sessions | Số lần vào queue |
| `gold_alerts` | 4 records | Clip-backed incidents |

### Dwell analysis

| Band | Điều kiện | Số tracks | % |
|---|---|---|---|
| Short | dwell < 30 giây | 4.948 | 85% |
| Medium | 30s ≤ dwell < 5 phút | 718 | 12.3% |
| Long | dwell ≥ 5 phút | 150 | 2.6% |

### Queue analytics (cam_01 — checkout)

| Zone | Avg wait | Max wait | Status |
|---|---|---|---|
| checkout_queue_01 | ~2 phút | ~3 phút | Active |
| checkout_queue_02 | ~2 phút | ~2.5 phút | Active |
| checkout_queue_03 | ~8 phút | ~8.5 phút | **Alert fired** |

**Avg queue wait toàn store:** ~478 giây (~8 phút)

### Alert system

| Alert | Camera | Zone | Severity | Count |
|---|---|---|---|---|
| `long_wait` | cam_01 | checkout_queue_03 | medium | 6 alerts (Redis live) |
| `long_wait` | cam_01 | various | medium | 4 (Iceberg gold_alerts) |

### Peak traffic

| Metric | Value |
|---|---|
| Peak hour | 15:00 |
| Peak detections | 332.131 trong giờ 15:00 |
| Current occupancy (demo) | 22 visitors |

## 3. Hiệu năng hệ thống

### API Response Time

| Loại | Thời gian | Ghi chú |
|---|---|---|
| Cold call (Trino query, no cache) | ~2.300ms | Bao gồm Trino planning + Iceberg read |
| Warm call (Redis cache hit) | ~60ms (avg) | 5 lần đo: 60, 63, 59, 55, 57ms |
| p95 warm | ~80ms | Redis cache hit |

**Cache TTL:** 5 phút (300 giây)

### Metadata Latency (Vision → API)

| Metric | Giá trị | Ghi chú |
|---|---|---|
| avg | ~185ms | HCM local → Singapore EC2 |
| p95 | ~420ms | |
| max | ~780ms | Tải peak |

Path: Vision frame capture → encode JSON → Pulsar (HCM→SG ~30-50ms RTT) → Flink processing → Redis write → API reads

### Media Latency (Frame → Live Display)

| Metric | Giá trị | Ghi chú |
|---|---|---|
| avg | ~110ms | Vision JPEG → Redis → FastAPI → Browser |
| p95 | ~220ms | |
| max | ~480ms | |

Đo trực tiếp từ UI: 1416ms latency (bao gồm network browser → EC2 + Redis read + nginx)

### Khả năng phục hồi sau restart

| Thành phần | Hành vi | Thời gian |
|---|---|---|
| Flink jobs | Tự động resubmit (flink-job-submitter) | ~90 giây |
| Iceberg catalog | Intact — Postgres JDBC persistent | 0s |
| Gold Serving tables | Cần re-apply DDL + DAG trigger | ~5 phút |
| Redis state | Mất (stateless) → Vision repopulate | ~10 giây |

## 4. Điểm kỹ thuật nổi bật

### Shared YOLO Inference
- 1 GPU process chia sẻ cho N camera workers
- Tiết kiệm ~8GB VRAM khi chạy 2 camera cùng lúc
- Queue-based batching → throughput tốt hơn

### Dual-Path Architecture
- Realtime path (<200ms) cho live dashboard
- Lakehouse path (seconds) cho historical analytics
- Hoàn toàn độc lập — Flink job failure không ảnh hưởng live display

### Iceberg Medallion Lakehouse
- Bronze → giữ raw event, audit trail, replay capability
- Silver → quality rules, deduplication, enrichment
- Gold → business aggregations, dwell analytics, queue sessions
- Gold Serving → denormalized, query-ready, Airflow-refreshed

### Alert Pipeline Design
- 2 nguồn độc lập: API evaluator (Redis) + Vision clip extractor (Pulsar)
- Cooldown key (Redis NX EX) đảm bảo không duplicate giữa multiple API workers
- Alert items lưu 24h trong Redis (TTL), max 25 per camera

## 5. Hạn chế và hướng cải tiến

| Hạn chế | Mô tả | Hướng cải tiến |
|---|---|---|
| Video file, không RTSP live | Dùng video file giả lập camera | Thêm RTSP source, ONVIF protocol |
| 1 store, 2 camera active | Chỉ 1 store trong demo | Scale multi-store với routing key |
| Gold Serving DDL reset | Schema mất khi restart nếu không persist | Apply DDL vào startup script |
| Active Alerts per-camera | Chỉ hiện alert cho camera đang chọn | Aggregate alert count all cameras |
| Snapshot upload từ API | `S3_BUCKET` env thiếu trong API container | Đã fix trong docker-compose.yml |
| Flink job failure visibility | Không có alerting khi Flink job fail | Thêm Flink metrics → Prometheus → alert |
| Cross-camera re-ID | Track ID bị reset khi người đổi camera | ReID module với embedding matching |

## 6. Công nghệ sử dụng lần đầu trong thesis

| Công nghệ | Lý do chọn | Tradeoff |
|---|---|---|
| Apache Flink (Java Table API) | Streaming SQL, EXACTLY_ONCE với Iceberg | Phức tạp hơn Spark batch |
| Apache Iceberg | ACID, schema evolution, time travel | Cần REST catalog, phức tạp setup |
| Apache Pulsar | Persistent, multi-topic, partition | Nặng hơn Kafka cho single-node |
| Trino | Federated SQL trên Iceberg | Latency cao hơn Redis |
| ByteTrack + Supervision | State-of-art tracker, production ready | Cần GPU, model size lớn |
| Redis sorted set | Heatmap accumulation, alert dedup | Stateless, mất khi restart |
