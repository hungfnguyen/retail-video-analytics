# Retail Video Analytics — Realtime + Lakehouse

> Đồ án tốt nghiệp Data Engineering: hệ thống realtime pipeline thu thập & xử lý metadata video cho chuỗi bán lẻ.
> Stack: **YOLO11 + BoTSORT → Pulsar → Flink (dual-path) → Redis + Iceberg/S3 → Trino → FastAPI → Frontend**

---

## Yêu cầu hệ thống

- Docker & Docker Compose
- Python 3.12+ (vision module)
- Java 11+ & Maven 3.9+ (chỉ cần khi build lại Flink jobs)
- GPU CUDA 12.4 (tùy chọn, YOLO11 chạy được trên CPU)

---

## 📦 Thành phần chính

| Layer | Công nghệ | Mô tả |
|-------|-----------|-------|
| **Vision AI** | YOLO11 (Ultralytics) + BoTSORT/ByteTrack | Detect & track người, xuất JSON metadata |
| **Media Plane** | OpenCV + S3/MinIO | Upload sampled JPEG 1fps và optional alert MP4 clips |
| **Transport** | Apache Pulsar 3.3.2 | Message broker với `Key_Shared` theo `camera_id` |
| **Stream Compute** | Apache Flink 1.18 | Xử lý Bronze → Silver → Gold streaming |
| **Lakehouse** | Apache Iceberg + REST Catalog | Table format trên S3 (MinIO cho local demo) |
| **Query Engine** | Trino 418 | SQL analytics với Iceberg connector |
| **Serving UI** | Frontend SPA + FastAPI | Live monitoring, analytics, system views |

## 📁 Runtime Layout

```text
services/
├── vision/          # YOLO11 + tracker + Pulsar producer
└── flink-jobs/      # Java Flink jobs: Bronze, Silver, Gold Track Summary

infrastructure/
├── pulsar/
├── flink/
├── minio/
├── trino/
```

---

## Kiến trúc

```
Vision (YOLO11 + BoTSORT)
  │
  ├── metadata JSON → Pulsar (persistent://retail/metadata/events)
  │                         │
  │           ┌─────────────┴──────────────┐
  │           │                            │
  │    [Lakehouse Path]              [Realtime Path]
  │    Table API, ckpt 60s          DataStream API, ckpt 10s
  │    latency 2-3 min              latency <5s
  │           │                            │
  │    Bronze → Iceberg              Redis live_count
  │    Silver → Iceberg              Redis heatmap (ZINCRBY)
  │    Gold   → Iceberg              Redis active tracks (HSET)
  │           │                      DLQ → Pulsar dlq-events
  │    Trino → FastAPI                     │
  │    (historical)                  FastAPI → Frontend
  │
  └── sampled JPEG / alert MP4 → MinIO (S3)
```

---

## Cổng dịch vụ

| Service | Port | URL | Credentials |
|---------|------|-----|-------------|
| Flink UI | 8081 | http://localhost:8081 | — |
| Trino | 8083 | http://localhost:8083 | — |
| Pulsar Admin | 8084 | http://localhost:8084 | — |
| MinIO Console | 9001 | http://localhost:9001 | minioadmin / minioadmin123 |
| MinIO API | 9000 | http://localhost:9000 | — |
| Iceberg REST | 8181 | http://localhost:8181 | — |
| Pulsar Broker | 6650 | pulsar://localhost:6650 | — |
| Redis | 6379 | redis://localhost:6379 | — |

---

## Verify hệ thống — từng layer

### Infrastructure health

```bash
# Tất cả services phải healthy / running
docker compose ps

# Log của 1 service cụ thể
docker compose logs flink-jobmanager
docker compose logs redis
```

### Pulsar — topics & messages

```bash
# Kiểm tra topics đã tạo
docker exec pulsar-broker bin/pulsar-admin topics list retail/metadata

# Xem stats topic chính
docker exec pulsar-broker bin/pulsar-admin topics stats \
  persistent://retail/metadata/events

# Consume vài message để verify event_id
docker exec pulsar-broker bin/pulsar-client consume \
  persistent://retail/metadata/events \
  -s verify-sub -n 3

# DLQ stats
docker exec pulsar-broker bin/pulsar-admin topics stats \
  persistent://retail/metadata/dlq-events
```

### Flink — 4 jobs running

```bash
# Số jobs đang chạy (expected: 4)
curl -s http://localhost:8081/jobs/overview | python3 -m json.tool | grep state

# Hoặc kiểm tra trong browser: http://localhost:8081
```

### Redis — realtime state

```bash
# Live person count (cập nhật mỗi frame, TTL 5s)
docker exec redis redis-cli GET stats:count:cam_01

# Heatmap top cells (TTL 60s)
docker exec redis redis-cli ZREVRANGE heatmap:live:cam_01 0 10 WITHSCORES

# Active tracks (TTL 30s)
docker exec redis redis-cli KEYS "track:active:cam_01:*"

# Tất cả Redis keys
docker exec redis redis-cli KEYS "*"
```

### Iceberg — Bronze / Silver / Gold

```bash
# Query Bronze count
docker exec trino trino --execute \
  "SELECT COUNT(*) AS total FROM lakehouse.rva.bronze_raw"

# Query Silver count  
docker exec trino trino --execute \
  "SELECT camera_id, COUNT(*) AS detections FROM lakehouse.rva.silver_detections GROUP BY camera_id"

# Query Gold track summary
docker exec trino trino --execute \
  "SELECT track_id, duration_sec, frames FROM lakehouse.rva.gold_track_summary LIMIT 10"

# Kiểm tra event_id trong Bronze
docker exec trino trino --execute \
  "SELECT event_id, camera_id, frame_index FROM lakehouse.rva.bronze_raw LIMIT 5"
```

### MinIO — sampled frames & clips

```bash
# List sampled JPEG frames
docker exec mc mc ls --recursive local/warehouse/frames

# List alert clips
docker exec mc mc ls --recursive local/warehouse/clips

# Lấy signed URL cho 1 file (thay KEY bằng path thực)
docker exec mc mc share download local/warehouse/frames/2026-05-17/cam_01/...
```

### DLQ — invalid events

```bash
# Xem stats DLQ topic
docker exec pulsar-broker bin/pulsar-admin topics stats \
  persistent://retail/metadata/dlq-events

# Consume DLQ messages
docker exec pulsar-broker bin/pulsar-client consume \
  persistent://retail/metadata/dlq-events \
  -s dlq-verify-sub -n 3

# Inject 1 event lỗi để test DLQ
docker exec pulsar-broker bin/pulsar-client produce \
  persistent://retail/metadata/events \
  --messages '{"invalid": true, "missing_event_id": true}'
```

---

## 🌐 Cổng dịch vụ

| Service | Port | URL |
|---------|------|-----|
| **Flink UI** | 8081 | http://localhost:8081 |
| **Trino** | 8083 | http://localhost:8083 |
| **Pulsar Admin** | 8084 | http://localhost:8084 |
| **MinIO Console** | 9001 | http://localhost:9001 |
| **MinIO API** | 9000 | http://localhost:9000 |
| **Iceberg REST** | 8181 | http://localhost:8181 |
| **Pulsar Broker** | 6650 | pulsar://localhost:6650 |
| **FastAPI API** | 8000 | http://localhost:8000 |

---

## Frontend Delivery

Dashboard chính của hệ thống là frontend SPA.

- `/live`: video realtime, live count, active tracks, heatmap, health ngắn hạn
- `/analytics`: historical analytics đọc qua FastAPI từ Trino/Iceberg
- `/system`: trạng thái service và pipeline health

---

## 🔧 Vision Module Config

Cấu hình trong `services/vision/config/settings.py` hoặc qua `services/vision/.env`:

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `S3_ENDPOINT` | `http://localhost:9000` | MinIO endpoint (Vision trên host) |
| `S3_ACCESS_KEY` | `minioadmin` | Access key |
| `S3_SECRET_KEY` | `minioadmin123` | Secret key |
| `S3_BUCKET` | `warehouse` | Bucket |
| `S3_REGION` | `us-east-1` | Region |
| `CAMERA_ID` | `cam_01` | Camera ID (single-cam mode) |
| `STORE_ID` | `store_01` | Store ID (single-cam mode) |
| `MODEL_NAME` | `yolo11l.pt` | YOLO model |
| `TRACKER_TYPE` | `botsort` | `botsort` hoặc `bytetrack` |
| `CONF_THRES` | `0.25` | Confidence threshold |

---

## Cấu trúc thư mục

```
retail-video-analytics/
├── configs/              # cameras.yaml, logging.yaml
├── data/videos/          # video1.mp4, video2.mp4
├── docs/                 # 14 tài liệu kiến trúc
├── infrastructure/       # Docker config: Pulsar, Flink, MinIO, Trino
├── packages/             # Shared Python packages
│   ├── core/             # Pydantic models, constants, settings, time utils
│   ├── messaging/        # Pulsar producer/consumer wrappers
│   └── storage/          # S3 client, Redis client
├── services/
│   ├── vision/           # YOLO detect → track → emit (Python)
│   └── flink-jobs/       # Flink Java jobs (Bronze, Silver, Gold, Realtime)
├── tests/                # unit/, integration/, e2e/
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```

---

## Troubleshooting

### Không thấy data trong Trino
Flink checkpoint mặc định 60s → chờ ít nhất 90 giây sau khi chạy Vision.

### Flink job FAILED
```bash
# Xem log Flink
docker compose logs flink-jobmanager | tail -50
docker compose logs flink-taskmanager | tail -50

# Xem exception trong Flink UI → job → exceptions
```

### Redis không có data
```bash
# Kiểm tra RealtimeMetricsJob đang RUNNING trong Flink UI
# Kiểm tra Redis container đang chạy
docker compose exec redis redis-cli ping
```

### Reset do schema thay đổi (thêm cột event_id)
```bash
docker compose down -v    # Xóa cả volumes (Iceberg data)
docker compose up -d --build
```

### Port conflict
Sửa port mapping trong `docker-compose.yml`:
- Pulsar admin: `8084:8080` (8080 thường bị chiếm)
- Trino: `8083:8080` (8080 thường bị chiếm)
- Flink UI: `8081:8081`

---

## Tài liệu

- [Kiến trúc đích](docs/01_TARGET_ARCHITECTURE.md)
- [Data flow & contracts](docs/02_DATA_FLOW_AND_CONTRACTS.md)
- [Streaming pipeline — dual-path](docs/03_STREAMING_PIPELINE.md)
- [Lakehouse design (Bronze/Silver/Gold)](docs/04_LAKEHOUSE_DESIGN.md)
- [Flink API Guide — DataStream vs Table API](docs/13_FLINK_API_GUIDE.md)
- [Vision multi-camera flow](docs/11_VISION_MULTI_CAMERA_FLOW.md)
- [Implementation roadmap (M0-M8)](docs/08_IMPLEMENTATION_ROADMAP.md)

---

## Contributors

- [Nguyễn Tấn Hùng](https://github.com/hungfnguyen)
- [Nguyễn Công Đôn](https://github.com/CongDon1207)
