# Hướng Dẫn Vận Hành - Phase 1 (Refactored Structure)

Tài liệu này hướng dẫn các bước chạy hệ thống sau khi đã hoàn thành **Phase 1: Refactor Structure**. Mục tiêu là đảm bảo luồng dữ liệu từ tiểu luận chuyên ngành vẫn chạy tốt trong cấu trúc thư mục `services/` mới.

---

## 1. Khởi chạy Hạ tầng (Infrastructure)

Mọi dịch vụ hạ tầng (Pulsar, Flink, MinIO, Trino, Grafana) vẫn được quản lý qua Docker Compose tại root.

```bash
# Đứng tại root project
docker compose up -d --build
```

**Lưu ý:** 
- Chờ khoảng 1-2 phút để các container `healthy`.
- Container `flink-job-submitter` sẽ tự động submit các bản JAR từ `services/flink-jobs/java/target/` vào Flink cluster.

---

## 2. Cài đặt Môi trường Python

Vision module hiện dùng workspace `uv`.

```bash
# Cài uv nếu máy chưa có
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies cho toàn bộ workspace
uv sync --all-packages
```

---

## 3. Chạy Vision Service (Module xử lý Video)

Sau khi refactor, code vision đã nằm trong `services/vision/`.

```bash
uv run --package rva-vision python services/vision/main.py
```

**Kiểm tra tại console:**
- Bạn sẽ thấy log của YOLO11 bắt đầu load model.
- Log `PulsarEmitter` báo kết nối thành công tới `pulsar://localhost:6650`.
- Nếu `media_upload_enabled: true`, log sẽ báo `FrameSampler enabled`.
- Mỗi 30 frame sẽ có log gửi metadata thành công.

---

## 4. Kiểm tra Dữ liệu (Verification)

### 4.1. Kiểm tra Pulsar (Ingestion)
Xem thống kê topic metadata:
```bash
docker exec pulsar-broker bin/pulsar-admin topics stats persistent://retail/metadata/events
```

Xem topic media artifact nếu bật media upload:
```bash
docker exec pulsar-broker bin/pulsar-admin topics stats persistent://retail/metadata/media-events
```

### 4.2. Kiểm tra Flink (Processing)
Truy cập [http://localhost:8081](http://localhost:8081) để xác nhận 3 jobs hiện tại (Bronze, Silver, Gold Track Summary) đang ở trạng thái `RUNNING`.

### 4.3. Truy vấn Trino (Storage)
Đợi khoảng 60-90 giây (để Flink hoàn thành checkpoint), sau đó chạy lệnh:
```bash
# Kiểm tra lớp Bronze
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.bronze_raw"

# Kiểm tra lớp Silver
docker exec trino trino --execute "SELECT * FROM lakehouse.rva.silver_detections LIMIT 10"
```

### 4.4. Xem Dashboard (Visualization)
Truy cập [http://localhost:3000](http://localhost:3000):
- Login: `admin` / `admin`.
- Mở Dashboard: **RVA - People Overview**.
- Xác nhận các biểu đồ đang nhảy dữ liệu realtime.

### 4.5. Kiểm tra sampled frames và alert clips trên MinIO

```bash
# Sampled JPEG frames
docker exec mc mc ls --recursive local/warehouse/frames

# Alert MP4 clips, chỉ có nếu bật alert_clip_enabled
docker exec mc mc ls --recursive local/warehouse/clips
```

Để test clip nhanh, sửa `configs/cameras.yaml`:

```yaml
settings:
  alert_clip_enabled: true
  alert_density_threshold: 1
```

Sau khi test, đưa threshold về `10` hoặc tắt `alert_clip_enabled` để tránh tạo nhiều clip.

---

## 5. Các lưu ý sau Refactor

1. **Config camera chính:** Sửa `configs/cameras.yaml` cho multi-camera, S3 media upload và alert clip.
2. **Path file .env:** File `.env` của vision hiện nằm tại `services/vision/.env`, dùng cho fallback hoặc override.
3. **Video test:** Các file video mẫu nên được đặt trong `data/videos/` ở root.
4. **Logs:** Nếu có lỗi, hãy kiểm tra log của từng service:
   - `docker logs flink-jobmanager`
   - `docker logs pulsar-broker`
   - `docker logs flink-job-submitter` (xem lý do job không submit được).
