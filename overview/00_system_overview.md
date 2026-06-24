# Retail Video Analytics — Tổng Quan Hệ Thống

## 1. Giới thiệu đề tài

**Retail Video Analytics (RVA)** là hệ thống phân tích video bán lẻ theo thời gian thực, được xây dựng như luận văn tốt nghiệp chuyên ngành **Kỹ thuật Dữ liệu (Data Engineering)**. Hệ thống áp dụng Computer Vision để trích xuất dữ liệu hành vi khách hàng từ camera giám sát, sau đó xử lý qua pipeline dữ liệu hiện đại theo kiến trúc Medallion Lakehouse.

**Mục tiêu kỹ thuật chính:**
- Trích xuất metadata có cấu trúc từ luồng video camera (không lưu raw video)
- Xây dựng streaming pipeline từ nguồn (Vision) → broker (Pulsar) → xử lý (Flink) → lưu trữ (Iceberg/S3)
- Phục vụ dashboard realtime (Redis) và analytics lịch sử (Trino + FastAPI)
- Triển khai hybrid: Vision chạy local GPU, hạ tầng dữ liệu chạy trên AWS EC2

## 2. Công nghệ sử dụng

| Tầng | Công nghệ | Vai trò |
|---|---|---|
| Computer Vision | Python + YOLO11l + Supervision + Roboflow Trackers (ByteTrack) | Phát hiện, tracking người |
| Message Broker | Apache Pulsar 3.3.2 | Vận chuyển metadata event |
| Stream Processing | Apache Flink 1.19 (Java + Table API) | Xử lý stream, ghi Iceberg |
| Realtime Store | Redis 7 | State tracking, heatmap, alert |
| Table Format | Apache Iceberg | Định dạng bảng ACID cho lakehouse |
| Object Storage | AWS S3 (`s3-retail-video-analytics`) | Lưu Iceberg warehouse + media |
| Catalog | Iceberg REST Catalog (Postgres-backed) | Quản lý metadata bảng |
| Query Engine | Trino 468 | SQL analytics trên Iceberg |
| Workflow | Apache Airflow 2.x | Lên lịch refresh Gold Serving |
| Backend API | FastAPI (Python) | Backend-for-frontend |
| Frontend | React 18 + TypeScript + Vite | Dashboard Live / Analytics / System |
| Reverse Proxy | Nginx | Serve frontend + proxy API |
| Infrastructure | Docker Compose | Orchestration trên EC2 |

## 3. Phạm vi triển khai

```
[Máy local - GPU RTX 3060/4060]          [AWS EC2 ap-southeast-1 - 52.74.215.164]
┌─────────────────────────┐               ┌──────────────────────────────────────┐
│  Vision Service         │               │  Docker Compose Stack                │
│  - YOLO11l inference    │──Pulsar────▶  │  - pulsar-broker (6650)              │
│  - ByteTrack tracking   │               │  - flink-jobmanager (8081)           │
│  - Zone detection       │──Redis ─────▶ │  - flink-taskmanager                 │
│  - Frame annotating     │               │  - redis (16379)                     │
│  - Alert clip extract   │──S3 ────────▶ │  - iceberg-rest (8181)               │
└─────────────────────────┘               │  - trino (8083)                      │
                                          │  - postgres (5432, internal only)    │
                                          │  - airflow (8085)                    │
                                          │  - api (8000, behind nginx)          │
                                          │  - nginx (80)                        │
                                          └──────────────────────────────────────┘
                                                          │
                                          [Browser] http://52.74.215.164
```

## 4. Dữ liệu được xử lý

Hệ thống xử lý **video file** (không phải live RTSP) từ 3 camera giả lập:

| Camera | Vai trò | Zone được cấu hình |
|---|---|---|
| cam_01 | Checkout (quầy thanh toán) | 3 vùng hàng chờ (checkout_queue_01/02/03) |
| cam_02 | Aisle (lối đi) | aisle_01, promo_area_02, đường vạch aisle_crossing_01 |
| cam_03 | Entrance (cửa vào) | (disabled trong demo) |

Video source: `data/videos/video1.mp4`, `video2.mp4` — chạy theo vòng lặp liên tục để giả lập camera thực.

## 5. Kết quả đạt được (demo 2026-06-23)

| Chỉ số | Giá trị |
|---|---|
| Silver detections (tổng) | ~363.000 records (1 ngày dữ liệu) |
| Unique tracks (dwell-based) | 5.816 tracks (short 4.948 / medium 718 / long 150) |
| Peak hour | 15:00 với 332.131 detections |
| Active alerts (Redis) | 6 alerts `long_wait` trên cam_01 / checkout_queue_03 |
| API response — cold (Trino) | ~2.300ms |
| API response — warm (Redis cache) | ~60ms |
| Avg queue wait | ~478 giây (~8 phút) tại checkout_queue_03 |
