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

Sử dụng file `setup.txt` tại root để cài đặt các thư viện cho Vision module.

```bash
# Tạo và kích hoạt venv (nếu chưa có)
python3 -m venv venv
source venv/bin/activate

# Cài đặt dependencies
pip install -r setup.txt
```

---

## 3. Chạy Vision Service (Module xử lý Video)

Sau khi refactor, code vision đã nằm trong `services/vision/`.

```bash
# Chạy trực tiếp từ root (đảm bảo PYTHONPATH hoặc settings nhận diện đúng)
python3 services/vision/main.py
```

**Kiểm tra tại console:**
- Bạn sẽ thấy log của YOLO11 bắt đầu load model.
- Log `PulsarEmitter` báo kết nối thành công tới `pulsar://localhost:6650`.
- Các dòng `Frame emitted` hiện lên liên tục.

---

## 4. Kiểm tra Dữ liệu (Verification)

### 4.1. Kiểm tra Pulsar (Ingestion)
Xem thống kê topic để biết dữ liệu có đang chảy vào không:
```bash
docker exec pulsar-broker bin/pulsar-admin topics stats persistent://retail/metadata/events
```

### 4.2. Kiểm tra Flink (Processing)
Truy cập [http://localhost:8081](http://localhost:8081) để xác nhận 8 jobs (Bronze, Silver, Gold) đang ở trạng thái `RUNNING`.

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

---

## 5. Các lưu ý sau Refactor

1. **Path file .env:** File `.env` của vision hiện nằm tại `services/vision/.env`. Nếu bạn sửa cấu hình camera, hãy sửa ở đây.
2. **Video test:** Các file video mẫu nên được đặt trong `data/videos/` ở root (đã được mount vào container nếu cần).
3. **Logs:** Nếu có lỗi, hãy kiểm tra log của từng service:
   - `docker logs flink-jobmanager`
   - `docker logs pulsar-broker`
   - `docker logs flink-job-submitter` (xem lý do job không submit được).
