# Retail Video Analytics (Lakehouse, Realtime)

> Realtime pipeline thu thập & xử lý **metadata video** cho chuỗi bán lẻ.
> Stack: **YOLO11 + BoTSORT → Pulsar → Flink → Iceberg on MinIO → Trino → Grafana**

![Architecture](docs/architecture.png)

---

## 📦 Thành phần chính

| Layer | Công nghệ | Mô tả |
|-------|-----------|-------|
| **Vision AI** | YOLO11 (Ultralytics) + BoTSORT/ByteTrack | Detect & track người, xuất JSON metadata (không đẩy khung hình) |
| **Transport** | Apache Pulsar 3.3.2 | Message broker với `Key_Shared` theo `camera_id` |
| **Stream Compute** | Apache Flink 1.18 | Xử lý Bronze → Silver → Gold streaming |
| **Lakehouse** | Apache Iceberg + REST Catalog | Table format trên MinIO (S3-compatible) |
| **Query Engine** | Trino 418 | SQL analytics với Iceberg connector |
| **Visualization** | Grafana 11.3 | Dashboards near-real-time |

---

## 🏗️ Kiến trúc

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Vision AI     │     │     Pulsar      │     │     Flink       │
│  YOLO11+BoTSORT │────▶│   (messages)    │────▶│ Bronze→Silver→  │
│   (detect/track)│     │                 │     │     Gold        │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
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
- Python 3.10+ (cho Vision module)
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

> 💡 **Tự động hóa**: Service `flink-job-submitter` sẽ tự động submit 8 Flink jobs (Bronze, Silver, 6 Gold) khi stack khởi động xong.

### 3. Setup Vision Module

```bash
# Tạo virtual environment
python -m venv venv
source venv/Scripts/activate  # Windows Git Bash

# Cài dependencies
pip install -r setup.txt
```

### 4. Chạy Vision AI

```bash
python vision/main.py
```

> Vision module tự động stream metadata vào Pulsar topic `persistent://retail/metadata/events`.

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

---

## 📊 Grafana Dashboards

Sau khi login Grafana (http://localhost:3000):

- **RVA - People Overview**: Detections/unique people theo phút và camera
- **RVA - Zone Dwell & Heatmap**: Visits và dwell time theo zone
- **RVA - Track Summary**: Track với duration, movement và confidence

---

## 🔧 Vision Module Config

Cấu hình trong `vision/config/settings.py` hoặc qua `.env`:

| Biến | Mặc định | Mô tả |
|------|----------|-------|
| `MODEL_NAME` | `yolo11l.pt` | Model YOLO (n/s/m/l/x) |
| `TRACKER_TYPE` | `botsort` | Tracker: `botsort` hoặc `bytetrack` |
| `CONF_THRES` | `0.25` | Ngưỡng confidence |
| `CLASS_FILTER` | `[0]` | Filter class (0=person) |
| `CAMERA_ID` | `cam_01` | ID camera |
| `STORE_ID` | `store_01` | ID cửa hàng |

---

## 📚 Tài liệu

- 📄 **Hướng dẫn chi tiết**: [`docs/guide.md`](docs/guide.md)
- 📄 **Luồng dữ liệu E2E**: [`docs/data-flow.md`](docs/data-flow.md)
- 📄 **Google Drive**: [Tài liệu dự án](https://drive.google.com/drive/folders/15HIuR8GIeGHsRPt7F2PeaChrG9XlMYoa?usp=sharing)

---

## 🛠️ Troubleshooting

### Kiểm tra Flink jobs

```bash
# Xem số lượng jobs đang chạy (expected: 8)
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

**📝 Last Updated:** December 1, 2025
