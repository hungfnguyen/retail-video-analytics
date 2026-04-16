# 🚀 Retail Video Analytics Pipeline - Hướng Dẫn End-to-End

> **Streaming Lakehouse Architecture**: Vision AI → Pulsar → Flink → Iceberg → Trino → Grafana

---

## 📋 Mục Lục

1. [Chuẩn bị Môi trường](#1-chuẩn-bị-môi-trường)
2. [Khởi chạy Pipeline](#2-khởi-chạy-pipeline)
3. [Chạy Vision AI](#3-chạy-vision-ai)
4. [Kiểm tra & Monitoring](#4-kiểm-tra--monitoring)
5. [Troubleshooting](#5-troubleshooting)

---

## 1. Chuẩn bị Môi trường

### 1.1. Tạo Virtual Environment (chỉ lần đầu)

```bash
python -m venv venv
```

### 1.2. Kích hoạt môi trường

```bash
# Windows (Git Bash/PowerShell):
source venv/Scripts/activate

# Windows (Command Prompt):
venv\Scripts\activate
```

### 1.3. Cài đặt Dependencies

```bash
pip install -r setup.txt
```

---

## 2. Khởi chạy Pipeline

### 2.1. Start toàn bộ stack

```bash
docker compose up -d --build
```

⏱️ **Chờ 1-2 phút** để các service khởi động.

### 2.2. Kiểm tra services

```bash
docker ps
```

**Kết quả mong đợi:** Tất cả containers ở trạng thái `healthy` hoặc `running`.

> 💡 **Tự động hóa**: Service `flink-job-submitter` sẽ tự động submit 8 Flink jobs (Bronze, Silver, 6 Gold) khi stack khởi động xong.

### 2.3. Verify jobs đang chạy

```bash
curl -s http://localhost:8081/jobs/overview | jq '.jobs | length'
# Kết quả: 8
```

Hoặc mở **Flink UI**: http://localhost:8081 → Xác nhận 8 jobs đang `RUNNING`.

---

## 3. Chạy Vision AI

Chạy Vision module để detect, track người từ video và **tự động stream vào Pulsar**:

```bash
python vision/main.py
```

> 💡 **Lưu ý**: `main.py` đã tích hợp `PulsarEmitter`, dữ liệu sẽ được gửi trực tiếp vào Pulsar topic `persistent://retail/metadata/events` mà không cần bước replay riêng.

**Controls:**
- `q` hoặc `ESC` - Dừng processing

---

## 4. Kiểm tra & Monitoring

### 4.1. Services & Ports

| Service | Port | URL |
|---------|------|-----|
| Flink UI | 8081 | http://localhost:8081 |
| Grafana | 3000 | http://localhost:3000 |
| Trino | 8082 | http://localhost:8082 |
| MinIO Console | 9001 | http://localhost:9001 |
| Pulsar Admin | 8084 | http://localhost:8084 |

### 4.2. Query dữ liệu với Trino

```bash
# Đếm records trong Bronze
docker exec trino trino --execute \
  "SELECT COUNT(*) FROM lakehouse.rva.bronze_raw"

# Xem data mẫu
docker exec trino trino --execute \
  "SELECT * FROM lakehouse.rva.bronze_raw LIMIT 5"
```

### 4.3. Grafana Dashboards

**URL:** http://localhost:3000 (login: `admin` / `admin`)

Các dashboard có sẵn:
- **RVA - People Overview**: Detections/unique people theo phút và camera
- **RVA - Zone Dwell & Heatmap**: Visits và dwell time theo zone
- **RVA - Track Summary**: Track với duration, movement và confidence

---

## 5. Troubleshooting

### Job không chạy hoặc bị FINISHED sớm

```bash
# Xem logs của job submitter
docker logs flink-job-submitter

# Xem logs JobManager
docker logs flink-jobmanager

# Restart job submitter
docker compose restart flink-job-submitter
```

### Data không xuất hiện trong Trino

**Nguyên nhân:** Flink checkpoint chưa commit (mặc định 60s).

**Giải pháp:** Chờ thêm 60-90 giây sau khi chạy vision.

### Reset toàn bộ pipeline

```bash
# Stop và xóa volumes
docker compose down -v

# Khởi động lại
docker compose up -d --build
```

---

## 📚 Tham Khảo Nhanh

### Flink Commands

```bash
# Xem danh sách jobs
docker exec flink-jobmanager ./bin/flink list

# Cancel job
docker exec flink-jobmanager ./bin/flink cancel <JOB_ID>
```

### Pulsar Commands

```bash
# Xem topic stats
docker exec pulsar-broker bin/pulsar-admin topics stats \
  persistent://retail/metadata/events

# Xem subscriptions
docker exec pulsar-broker bin/pulsar-admin topics subscriptions \
  persistent://retail/metadata/events
```

---

**📝 Last Updated:** December 1, 2025  
**🔖 Version:** 2.0.0


