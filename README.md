# Retail Video Analytics (Lakehouse, Realtime)

> Realtime pipeline thu thập & xử lý **metadata video** cho chuỗi bán lẻ.
> Stack: **YOLO11 + BoTSORT → Pulsar → Flink → Iceberg on MinIO → Trino → Grafana**

> Phase 1 refactor note: runtime code is under `services/`, while the original thesis E2E behavior is preserved. FastAPI now has a mock dashboard API skeleton; Redis, PostgreSQL, and Streamlit are not integrated yet.

![Architecture](docs/images/architecture.png)
- **RVA - Traffic Patterns**: Visits per hour x day-of-week v… visit duration theo time-of-day (ph?c v? planning ca l?m, khuy?n m?i)

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
| **Visualization** | Grafana 11.3 | Dashboards near-real-time |

## 📁 Runtime Layout

```text
services/
├── api/             # FastAPI dashboard gateway with mock Live API contract
├── vision/          # YOLO11 + tracker + Pulsar producer
└── flink-jobs/      # Java Flink jobs: Bronze, Silver, Gold Track Summary

infrastructure/
├── pulsar/
├── flink/
├── minio/
├── trino/
└── grafana/
```

---

## 🏗️ Kiến trúc

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Vision AI     │     │     Pulsar      │     │     Flink       │
│  YOLO11+BoTSORT │────▶│ metadata/events │────▶│ Bronze→Silver→  │
│   (detect/track)│     │                 │     │     Gold        │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
        │
        │ sampled JPEG / alert clip
        ▼
┌─────────────────┐
│   MinIO / S3    │
│ frames/, clips/ │
└─────────────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│    Grafana      │◀────│     Trino       │◀────│    Iceberg      │
│  (dashboards)   │     │   (SQL query)   │     │    (MinIO)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## ⚙️ Yêu cầu & Cài đặt

### Yêu cầu hệ thống
- Docker & Docker Compose
- Python 3.12+ (cho Vision module)
- (Tùy chọn) GPU CUDA 12.4 cho YOLO11

### 1. Clone & Setup

```bash
# Clone repository
git clone https://github.com/hungfnguyen/retail-video-analytics.git
cd retail-video-analytics

# Tạo file .env từ template
cp .env.example .env
# Chỉnh sửa .env với credentials của bạn
```

### 2. Khởi chạy Infrastructure

```bash
# Start toàn bộ stack (chờ 1-2 phút)
docker compose up -d --build

# Kiểm tra services
docker ps
```

> 💡 **Tự động hóa**: Service `flink-job-submitter` sẽ tự động submit 3 Flink jobs hiện tại (Bronze, Silver, Gold Track Summary) khi stack khởi động xong.

### 3. Setup Vision Module

```bash
# Cài uv (một lần)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies
uv sync --all-packages
```

### 4. Chạy Vision AI

```bash
uv run --package rva-vision python services/vision/main.py
```

> Vision module tự động stream metadata vào Pulsar topic `persistent://retail/metadata/events`.
> Khi `media_upload_enabled: true`, Vision cũng upload sampled frames vào `s3://warehouse/frames/...` và publish media artifact events vào `persistent://retail/metadata/media-events`.

### 5. Kiểm tra media upload trên MinIO

```bash
# List sampled JPEG frames
docker exec mc mc ls --recursive local/warehouse/frames

# List alert clips nếu đã bật alert_clip_enabled
docker exec mc mc ls --recursive local/warehouse/clips
```

Để test video clip upload, bật trong `configs/cameras.yaml`:

```yaml
settings:
  alert_clip_enabled: true
  alert_density_threshold: 1
```

Sau khi test xong nên đưa `alert_density_threshold` về giá trị thực tế hơn, ví dụ `10`, để tránh tạo quá nhiều clip.

---

## 🌐 Cổng dịch vụ

| Service | Port | URL |
|---------|------|-----|
| **Flink UI** | 8081 | http://localhost:8081 |
| **Grafana** | 3000 | http://localhost:3000 (admin/admin) |
| **Trino** | 8083 | http://localhost:8083 |
| **Pulsar Admin** | 8084 | http://localhost:8084 |
| **MinIO Console** | 9001 | http://localhost:9001 |
| **MinIO API** | 9000 | http://localhost:9000 |
| **Iceberg REST** | 8181 | http://localhost:8181 |
| **Pulsar Broker** | 6650 | pulsar://localhost:6650 |
| **FastAPI API** | 8000 | http://localhost:8000 |

---

## 📊 Grafana Dashboards

Sau khi login Grafana (http://localhost:3000):

- **RVA - People Overview**: Detections/unique people theo phút và camera
- **RVA - Zone Dwell & Heatmap**: Visits và dwell time theo zone
- **RVA - Track Summary**: Track với duration, movement và confidence

---

## 🔧 Vision Module Config

Cấu hình trong `services/vision/config/settings.py` hoặc qua `services/vision/.env`:

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `MODEL_NAME` | `yolo11l.pt` | Model YOLO (n/s/m/l/x) |
| `TRACKER_TYPE` | `botsort` | Tracker: `botsort` hoặc `bytetrack` |
| `CONF_THRES` | `0.25` | Ngưỡng confidence |
| `CLASS_FILTER` | `[0]` | Filter class (0=person) |
| `CAMERA_ID` | `cam_01` | ID camera |
| `STORE_ID` | `store_01` | ID cửa hàng |

Media upload cấu hình chính trong `configs/cameras.yaml`:

| Key | Mặc định | Mô tả |
|-----|----------|-------|
| `media_upload_enabled` | `true` | Bật media plane S3/MinIO |
| `s3_endpoint` | `http://localhost:9000` | Endpoint MinIO khi Vision chạy trên host |
| `s3_bucket` | `warehouse` | Bucket local dùng chung với Iceberg demo |
| `frame_sampling_enabled` | `true` | Upload sampled JPEG |
| `frame_sample_interval_sec` | `1` | 1 frame/giây/camera |
| `alert_clip_enabled` | `false` | Bật alert MP4 clip extractor |

---

## 📚 Tài liệu

- 📄 **Documentation index**: [`docs/README.md`](docs/README.md)
- 📄 **S3 Infrastructure design**: [`docs/10_S3_INFRASTRUCTURE.md`](docs/10_S3_INFRASTRUCTURE.md)
- 📄 **Phase 1 refactor note**: [`docs/note/REFACTOR_STRATEGY_PHASED_MIGRATION.md`](docs/note/REFACTOR_STRATEGY_PHASED_MIGRATION.md)

---

## 🛠️ Troubleshooting

### Kiểm tra Flink jobs

```bash
# Xem số lượng jobs đang chạy (expected: 3)
curl -s http://localhost:8081/jobs/overview | jq '.jobs | length'

# Hoặc mở Flink UI: http://localhost:8081
```

### Data không xuất hiện trong Trino

Flink checkpoint mặc định 60s, chờ 60-90 giây sau khi chạy vision.

```bash
# Query kiểm tra Bronze
docker exec trino trino --execute \
  "SELECT COUNT(*) FROM lakehouse.rva.bronze_raw"
```

### Grafana báo thiếu time field

- Đảm bảo truy vấn Timeseries trả về cột `time` kiểu TIMESTAMP (dùng `ts_hour`/`ts_minute`, tránh `HOUR(ts_hour)` hoặc chỉ `DATE(ts_hour)`).

### Reset toàn bộ

```bash
docker compose down -v
docker compose up -d --build
```

---

## 👥 Contributors

- [Nguyễn Tấn Hùng](https://github.com/hungfnguyen)
- [Nguyễn Công Đôn](https://github.com/CongDon1207)

---

**📝 Last Updated:** May 6, 2026
