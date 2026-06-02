# AGENT.md — Retail Video Analytics System Overview

> **Mục đích tài liệu này:** Cung cấp cho AI Agent (hoặc thành viên mới) toàn bộ bức tranh kiến trúc, thiết kế dữ liệu, và luồng vận hành của hệ thống — đủ để hiểu, điều hướng, và làm việc hiệu quả trên codebase mà không cần đọc từng dòng code.

---

## 1. Mục Tiêu Hệ Thống

Đây là một **Data Engineering Pipeline** phục vụ phân tích hành vi khách hàng trong siêu thị theo thời gian thực (real-time) và lịch sử (historical). Hệ thống không lưu trữ raw video — thay vào đó, **Computer Vision** được dùng để trích xuất metadata có cấu trúc (tọa độ vị trí, track ID, confidence) từ từng khung hình của camera, rồi toàn bộ pipeline xử lý, lưu trữ và phục vụ dữ liệu metadata đó.

**Trọng tâm kỹ thuật:**
- Ingest & Stream Processing (Apache Flink)
- Realtime low-latency serving (Redis)
- Lakehouse storage (Apache Iceberg trên AWS S3)
- SQL Analytics (Trino)
- API Gateway & Dashboard (FastAPI + React)

---

## 2. Kiến Trúc Tổng Thể

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          Camera / Video Files                           │
│                    (configs/cameras.yaml - cam_01, cam_02, ...)         │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Vision Service                                 │
│         YOLO11 detection  →  BoTSORT/ByteTrack tracking                 │
│                                                                         │
│   Output #1: Pulsar Event (metadata JSON)                               │
│   Output #2: Annotated JPEG  → runtime/live_frames/{camera_id}.jpg      │
│   Output #3: Frame Metadata  → runtime/live_frames/{camera_id}.json     │
│   Output #4: Sampled Frame   → AWS S3 frames/ (optional)                │
└──────────┬──────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      Apache Pulsar                                   │
│                                                                      │
│  Topic: persistent://retail/metadata/events       (main stream)      │
│  Topic: persistent://retail/metadata/media-events (sampled media)    │
│  Topic: persistent://retail/metadata/dlq-events   (dead-letter)      │
└──────────┬────────────────────────────────┬─────────────────────────┘
           │                                │
           ▼                                ▼
┌─────────────────────┐          ┌─────────────────────────────────────┐
│  Flink Realtime     │          │  Flink Lakehouse (Table API / SQL)  │
│  (DataStream API)   │          │                                     │
│                     │          │  BronzeIngestJob                    │
│  ParseValidate      │          │  SilverJob                          │
│  Deduplicate        │          │  GoldTrackSummaryJob                │
│  → Redis Sink       │          │  → Iceberg on AWS S3                │
│  → DLQ Sink         │          │                                     │
└────────┬────────────┘          └──────────────┬──────────────────────┘
         │                                      │
         ▼                                      ▼
┌─────────────────┐                   ┌─────────────────────┐
│     Redis       │                   │  Apache Iceberg     │
│  (Live State)   │                   │  (AWS S3 Lakehouse) │
└────────┬────────┘                   └──────────┬──────────┘
         │                                       │
         │                                       ▼
         │                              ┌─────────────────┐
         │                              │      Trino      │
         │                              │  (SQL Engine)   │
         │                              └──────────┬──────┘
         │                                         │
         └──────────────────┬──────────────────────┘
                            │
                            ▼
               ┌────────────────────────┐
               │       FastAPI          │
               │  (Backend-for-Frontend)│
               │                        │
               │  /live/{cam}/dashboard │
               │  /media/.../snapshot   │
               │  /media/.../stream     │
               │  /media/.../webrtc     │
               └────────────┬───────────┘
                            │
                            ▼
               ┌────────────────────────┐
               │    React Frontend      │
               │                        │
               │  Live Page             │
               │  Analytics Page        │
               │  System Page           │
               └────────────────────────┘
```

---

## 3. Các Thành Phần Chính (Components)

### 3.1 Vision Service (`services/vision/`)
- **Vai trò:** "Edge processor" — đọc từng frame từ video file hoặc camera stream, chạy model AI để phát hiện và track người.
- **Mô hình AI:** YOLO11 (`yolo11l.pt`) cho detection, BoTSORT hoặc ByteTrack cho object tracking qua các frame.
- **Luồng xử lý per-camera:**
  - `VideoFileReader` → Frame Queue (size=1, drop nếu backlog) → YOLO11 track → normalize → Publish
- **Config:** `configs/cameras.yaml` — mỗi camera có `camera_id`, `store_id`, `source_uri`, và các tham số model.
- **Worker model:** Mỗi camera chạy trong **một process riêng biệt**. Process chính (`main.py`) quản lý và restart worker nếu bị crash.
- **Ưu tiên frame tươi:** Queue có size=1, frame cũ bị drop dưới áp lực → hệ thống luôn xử lý frame gần nhất nhất có thể.

---

### 3.2 Apache Pulsar (Message Broker)
- **Vai trò:** Transport layer bền vững giữa Vision (producer) và Flink (consumer).
- **Partitioned by camera:** Topic `events` được partition theo số camera để đảm bảo thứ tự sự kiện của cùng 1 camera.
- **3 Topics:**
  | Topic | Mục đích |
  |---|---|
  | `persistent://retail/metadata/events` | Detection events chính từ Vision |
  | `persistent://retail/metadata/media-events` | Media artifact events (sampled frames, clips) |
  | `persistent://retail/metadata/dlq-events` | Sự kiện không hợp lệ (Dead-Letter Queue) |

---

### 3.3 Flink Streaming (`services/flink-jobs/java/`)

Pipeline Flink chia làm **2 luồng xử lý độc lập** đọc cùng 1 Pulsar topic:

#### Luồng Realtime (DataStream API)
| Bước | Mô tả |
|---|---|
| **ParseValidate** | Parse JSON, validate các trường bắt buộc. Sự kiện lỗi → DLQ side-output. |
| **Deduplicate** | Loại bỏ trùng lặp theo `event_id` dùng Flink Keyed State TTL 10 phút. |
| **RealtimeRedisSink** | Ghi 4 loại key vào Redis (chi tiết mục 4). |
| **DLQ Sink** | Sự kiện lỗi đóng gói kèm lý do, publish vào Pulsar DLQ topic. |

- **Checkpoint:** mỗi 10 giây
- **Latency:** Redis được cập nhật ngay sau khi mỗi record được xử lý.

#### Luồng Lakehouse (Table API / SQL)
| Job | Input | Output | Mục đích |
|---|---|---|---|
| `BronzeIngestJob` | Pulsar raw JSON | `lakehouse.rva.bronze_raw` | Audit trail — lưu toàn bộ payload thô |
| `SilverJob` | bronze_raw (streaming) | `lakehouse.rva.silver_detections` | Flatten và clean detection rows |
| `GoldTrackSummaryJob` | silver_detections (streaming) | `lakehouse.rva.gold_track_summary` | Aggregate lifecycle của mỗi track |

- **Checkpoint:** mỗi 60 giây (Bronze). Iceberg visibility phụ thuộc vào checkpoint commit.
- **Latency:** Cao hơn Realtime path — phù hợp cho phân tích lịch sử, không dùng cho dashboard live.

---

### 3.4 Redis (Realtime State Store)
- **Vai trò:** In-memory store cho dashboard live. Không phải nguồn lịch sử.
- **Tất cả key đều có TTL ngắn** → khi camera hoặc Flink job dừng, trạng thái tự động hết hạn và dashboard sẽ chuyển sang trạng thái "Warning".

| Redis Key Pattern | Kiểu dữ liệu | TTL | Nội dung |
|---|---|---|---|
| `stats:count:{camera_id}` | String | 5 giây | Số người hiện tại trong frame |
| `live:frame:{camera_id}` | String (JSON) | 10 giây | Metadata đầy đủ của frame mới nhất (bbox, track_id, centroid) |
| `heatmap:live:{camera_id}` | Sorted Set | 60 giây | Score của từng ô tọa độ lưới 64×48 |
| `track:active:{camera_id}:{track_id}` | Hash | 30 giây | Thông tin chi tiết của 1 người đang được track |

---

### 3.5 Apache Iceberg & AWS S3 (Lakehouse)
- **Catalog:** Iceberg REST (`iceberg-rest` container)
- **Storage:** `s3://retail-video-analytics-prod/lakehouse`
- **Query engine:** Trino

**3 Bảng Iceberg hiện tại:**

| Bảng | Mô tả | Partition |
|---|---|---|
| `lakehouse.rva.bronze_raw` | Raw JSON payload + extracted header fields | `store_id` |
| `lakehouse.rva.silver_detections` | Flattened detection rows, validated, deduplicated (`conf >= 0.4`) | `store_id`, `bucket(16, camera_id)`, `days(capture_ts)` |
| `lakehouse.rva.gold_track_summary` | Tổng hợp mỗi track: enter_ts, exit_ts, duration_sec, frame count | Iceberg v2, upsert enabled |

**Layout S3:**
```
s3://retail-video-analytics-prod/
├── lakehouse/    ← Iceberg warehouse
├── frames/       ← Sampled JPEG (optional)
└── clips/        ← Alert clips (optional, disabled by default)
```

---

### 3.6 Trino (SQL Query Engine)
- **Vai trò:** Thực thi SQL queries trên Iceberg tables trong S3.
- **Catalog:** `lakehouse` → namespace `rva`
- **Dùng cho:** Phân tích lịch sử, data quality checks, backfill validation.
- **Chưa có:** FastAPI analytics endpoints gọi Trino (là mục tiêu Phase 3 roadmap).

---

### 3.7 FastAPI (`services/api/`)
- **Vai trò:** Backend-for-Frontend — tổng hợp data từ Redis + local file media, phục vụ React.
- **Endpoints hiện tại:**
  | Endpoint | Mô tả |
  |---|---|
  | `GET /health` | API health check |
  | `GET /api/v1/live/{camera_id}/dashboard` | Live dashboard data (Redis + media metadata) |
  | `GET /media/live/{camera_id}/snapshot.jpg` | Ảnh chụp JPEG mới nhất |
  | `GET /media/live/{camera_id}/stream` | MJPEG stream (fallback) |
  | `POST /media/live/{camera_id}/webrtc/offer` | WebRTC signaling |

- **Fallback logic:** Nếu Redis không có dữ liệu, API đọc file `runtime/live_frames/{camera_id}.json` (ghi trực tiếp bởi Vision worker) để vẫn trả về FPS, processing metrics, count, dù Flink tạm dừng.
- **Pipeline Health Check:** Mỗi request `/dashboard` thực hiện TCP probe đến Pulsar, Flink, Redis, S3, Trino và báo cáo trạng thái kết nối.

---

### 3.8 React Frontend (`frontend/`)
| Page | Trạng thái | Nguồn dữ liệu |
|---|---|---|
| **Live** | Đầy đủ | FastAPI `/live/{cam}/dashboard` + WebRTC/MJPEG stream |
| **Analytics** | UI có sẵn, backend pending | Sẽ gọi FastAPI analytics endpoints (chưa triển khai) |
| **System** | UI có sẵn, metrics một phần | FastAPI `pipeline_health` từ Live endpoint |

---

## 4. Event Contract (Giao Thức Dữ Liệu)

Vision Service publish JSON event sau mỗi frame xử lý lên Pulsar:
```json
{
  "schema_version": "1.0",
  "event_id": "<deterministic UUID>",
  "pipeline_run_id": "<vision process run ID>",
  "frame_index": 123,
  "capture_ts": "2026-05-28T15:39:58.123Z",
  "source": {
    "store_id": "store_001",
    "camera_id": "cam_01",
    "source_type": "video_file"
  },
  "image_size": { "width": 1280, "height": 720 },
  "detections": [
    {
      "det_id": "123-0",
      "class": "person",
      "class_id": 0,
      "conf": 0.86,
      "track_id": 42,
      "bbox":      { "x1": 100, "y1": 120, "x2": 220, "y2": 420 },
      "bbox_norm": { "x": 0.078, "y": 0.166, "w": 0.093, "h": 0.416 },
      "centroid":      { "x": 160, "y": 270 },
      "centroid_norm": { "x": 0.125, "y": 0.375 }
    }
  ],
  "runtime": {
    "model_name": "yolo11l.pt",
    "tracker_type": "botsort"
  }
}
```

**Lý do normalize tọa độ (`bbox_norm`, `centroid_norm`):**
- Downstream consumer (Flink, FastAPI, React) có thể ánh xạ tọa độ vào bất kỳ kích thước màn hình hoặc lưới heatmap nào mà không cần biết resolution gốc của camera.

---

## 5. Thiết Kế Heatmap

Heatmap được tính theo 2 tầng:

**Tầng 1 — Raw Grid (64×48 cells):**
```
grid_x = floor(centroid_norm.x × 64)   (cột: 0–63)
grid_y = floor(centroid_norm.y × 48)   (hàng: 0–47)
```
- Flink ghi vào Redis ZSET: `zincrby heatmap:live:{camera_id} 1.0 "grid_x,grid_y"`
- FastAPI đọc top-80 cells theo score để trả về tọa độ heatmap cho frontend.

**Tầng 2 — Zone Grid (6×7 = 42 zones):**
- Phân chia toàn bộ khung hình thành 6 hàng (`A1, A2, B1, B2, C1, C2`) × 7 cột.
- FastAPI gộp scores của các ô lưới thô vào zone tương ứng và chuẩn hóa về thang 0–100.
- Phục vụ hiển thị "khu vực nóng" trong cửa hàng trên dashboard.

---

## 6. Luồng Dữ Liệu End-to-End

```
Camera/Video
    │
    │  [Frame by frame]
    ▼
YOLO11 + Tracker
    │
    │  [DetectionFrameEvent JSON]
    ├────────────────────────────────────────────────────────┐
    │  Pulsar Producer                                       │
    ▼                                                        │
Pulsar: retail/metadata/events                              │
    │                                                        │
    ├── [Flink Realtime Job]                                 │
    │       ParseValidate → Deduplicate → Redis              │
    │               │                                        │
    │               └─ [Invalid] → Pulsar DLQ               │
    │                                                        │
    └── [Flink Lakehouse Jobs]                               │
            BronzeIngestJob → bronze_raw (Iceberg/S3)        │
            SilverJob       → silver_detections (Iceberg/S3) │
            GoldTrackSummaryJob → gold_track_summary         │
                                  (Iceberg/S3, upsert)       │
                                                             │
Redis (live state)    Trino (SQL over Iceberg)               │
    │                         │                              │
    └──────────┬──────────────┘                              │
               ▼                                             │
           FastAPI                                           │
               │  /live/{cam}/dashboard                      │
               │  /media/.../stream ◄────────────────────────┘
               ▼                       runtime/live_frames/
           React                       (local JPEG files)
           Live UI
```

---

## 7. Cấu Trúc Thư Mục Dự Án

```
retail-video-analytics/
│
├── configs/
│   └── cameras.yaml              ← Cấu hình camera (store_id, source, model params)
│
├── services/
│   ├── vision/                   ← Python Vision worker (YOLO + tracker + Pulsar)
│   │   ├── main.py               ← Process manager, spawn 1 worker per camera
│   │   ├── worker.py             ← Per-camera processing loop
│   │   ├── reader.py             ← VideoFileReader with frame queue
│   │   ├── detect/               ← YOLO inference wrapper
│   │   ├── track/                ← Tracker integration
│   │   ├── emit/                 ← Pulsar producer
│   │   └── media/                ← Live JPEG writer, S3 uploader
│   │
│   ├── api/                      ← Python FastAPI backend
│   │   └── src/rva_api/
│   │       ├── api/v1/live.py    ← Live dashboard endpoint
│   │       ├── api/v1/system.py  ← System health endpoint
│   │       ├── api/media/        ← Media serving (MJPEG, WebRTC, snapshot)
│   │       └── schemas/          ← Pydantic response models
│   │
│   └── flink-jobs/
│       └── java/                 ← Java Flink jobs
│           └── src/main/java/org/rva/
│               ├── BronzeIngestJob.java       ← Raw ingest to Iceberg
│               ├── silver/SilverJob.java      ← Flatten detections
│               ├── gold/GoldTrackSummaryJob.java ← Track aggregation
│               └── realtime/RealtimeMetricsJob.java ← Realtime Redis job
│
├── packages/
│   ├── core/                     ← Shared Python config utilities
│   ├── messaging/                ← Pulsar client wrapper
│   └── storage/                  ← Redis client wrapper
│
├── frontend/                     ← React dashboard (Vite)
│
├── infrastructure/               ← IaC, Terraform, AWS configs
├── aws/                          ← IAM policies, S3 setup scripts
├── configs/                      ← Camera YAML, model configs
├── data/videos/                  ← Sample video files for local testing
├── runtime/live_frames/          ← Vision ghi annotated JPEG ở đây (runtime)
├── docker-compose.yml            ← Infrastructure stack
├── docs/                         ← Architecture documentation (14 files)
├── CHANGELOG.md
└── AGENT.md                      ← File này
```

---

## 8. Hạ Tầng Docker Compose

| Service | Port | Vai trò |
|---|---|---|
| `pulsar-broker` | 6650, 8080 | Message broker & admin |
| `pulsar-init` | — | Tạo topics khi khởi động |
| `flink-jobmanager` | 8081 | Flink REST API & job coordination |
| `flink-taskmanager` | — | Thực thi Flink tasks |
| `flink-job-submitter` | — | Submit JARs lên Flink cluster khi start |
| `redis` | 6379 | In-memory state store |
| `iceberg-rest` | 8181 | Iceberg REST catalog |
| `trino` | 8083 | SQL query engine |

**Vision, FastAPI, Frontend:** Chạy trực tiếp trên host (không trong Docker) để dễ iterate và tận dụng GPU local.

---

## 9. AWS S3 Infrastructure

| Item | Giá trị |
|---|---|
| Bucket | `retail-video-analytics-prod` |
| Region | `ap-southeast-2` |
| Iceberg warehouse | `s3a://retail-video-analytics-prod/lakehouse` |

**IAM permissions cần thiết:** `s3:ListBucket`, `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` trên bucket.

**Tất cả biến môi trường S3/Iceberg phải được set đồng nhất cho:**
`flink-jobmanager` + `flink-taskmanager` + `flink-job-submitter` + `iceberg-rest` + `trino` + host Vision service.

---

## 10. Thiết Kế & Trade-off Quan Trọng

| Quyết định | Lý do |
|---|---|
| Không lưu raw video vào lakehouse | Metadata nhỏ hơn, queryable, đúng với mục tiêu Data Engineering |
| Video bytes tách khỏi Flink/Redis | Media là dữ liệu media-plane, không phải stream analytics state |
| Redis cho live state | Low-latency, TTL tự dọn dẹp, phù hợp cho dashboard |
| Iceberg trên S3 | Table snapshots, schema evolution, Trino compatibility |
| DataStream API cho Realtime, Table API cho Lakehouse | DataStream: custom DLQ side-output, Redis sink. Table API: SQL joins, Iceberg DDL native |
| Frame queue size=1, drop old frames | Frame tươi quan trọng hơn frame đầy đủ trong video analytics realtime |
| WebRTC first, MJPEG fallback | Trình duyệt hiện đại dùng WebRTC; MJPEG đơn giản và luôn hoạt động |
| Normalized bbox & centroid | Downstream mapping tọa độ không phụ thuộc vào resolution gốc của camera |

---

## 11. Trạng Thái Triển Khai (Tính đến Tháng 6/2026)

### ✅ Đã Hoàn Thành
- Multi-camera video processing (Vision workers per camera)
- Pulsar metadata topics (events, media-events, dlq-events)
- Flink Realtime Job: parse, validate, deduplicate, DLQ, Redis sink
- Flink Lakehouse Jobs: Bronze → Silver → Gold track summary
- Iceberg warehouse trên AWS S3 với 3 tables
- Trino SQL access
- FastAPI: Live dashboard API, WebRTC/MJPEG media serving
- React Frontend: Live page đầy đủ; Analytics và System page có UI

### 🔧 Đang Thiếu / Roadmap
| Phase | Hạng mục |
|---|---|
| Phase 2 | Gold tables mới: camera minute metrics, hourly heatmap, daily store summary |
| Phase 3 | FastAPI analytics endpoints gọi Trino (`/api/v1/analytics/...`) |
| Phase 4 | System health API đầy đủ cho tất cả services |
| Phase 5 | Alert data product (high-density, camera stale, DLQ alerts) |
| Phase 6 | Đo lường latency end-to-end, GPU/CPU resource metrics |

---

## 12. Hướng Dẫn Chạy Cục Bộ (Tóm Tắt)

```bash
# 1. Cài dependencies
uv sync --all-packages
cd frontend && npm install && cd ..

# 2. Cấu hình AWS
cp .env.example .env          # Điền S3 credentials
aws sts get-caller-identity   # Verify

# 3. Khởi động infrastructure (Docker)
docker compose up -d --build
docker compose ps             # Verify tất cả service UP

# 4. Khởi động Vision worker (host)
uv run --package rva-vision python services/vision/main.py

# 5. Khởi động FastAPI (host)
uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000

# 6. Khởi động Frontend (host)
cd frontend && npm run dev    # http://localhost:5173

# 7. Kiểm tra pipeline
curl http://localhost:8081/jobs/overview                                    # Flink jobs
docker exec redis redis-cli GET stats:count:cam_01                          # Redis
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.bronze_raw"  # Iceberg
curl http://localhost:8000/api/v1/live/cam_01/dashboard                    # FastAPI
```

---

## 13. Checklist Verification

| Area | Lệnh kiểm tra |
|---|---|
| Vision hoạt động | File `runtime/live_frames/cam_01.jpg` được cập nhật liên tục |
| Pulsar nhận events | `curl http://localhost:8080/admin/v2/persistent/retail/metadata/events/stats` |
| Flink 4 jobs running | `curl -s http://localhost:8081/jobs/overview` |
| Redis có data | `docker exec redis redis-cli GET stats:count:cam_01` |
| Heatmap có data | `docker exec redis redis-cli ZREVRANGE heatmap:live:cam_01 0 10 WITHSCORES` |
| Bronze có rows | `docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.bronze_raw"` |
| Silver có rows | `docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.silver_detections"` |
| Gold có rows | `docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.gold_track_summary"` |
| API live endpoint | `curl http://localhost:8000/api/v1/live/cam_01/dashboard` |
| S3 có Iceberg data | `aws s3 ls s3://retail-video-analytics-prod/lakehouse/ --recursive \| head` |

---

*Tài liệu này được tự động sinh ra bởi AI Agent và phản ánh trạng thái kiến trúc tại thời điểm phân tích. Cập nhật tài liệu này mỗi khi có thay đổi kiến trúc lớn.*
