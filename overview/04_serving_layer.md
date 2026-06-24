# Serving Layer — FastAPI + React Dashboard

## 1. Tổng quan

FastAPI đóng vai trò Backend-for-Frontend (BFF): một backend API duy nhất phục vụ toàn bộ nhu cầu của React dashboard, bao gồm cả live state (từ Redis) và historical analytics (từ Trino → Gold Serving Iceberg).

**Vị trí code:** `services/api/src/rva_api/`

## 2. API Endpoints

| Endpoint | Method | Mô tả |
|---|---|---|
| `GET /health` | — | Health check API |
| `GET /api/v1/live/{camera_id}/dashboard` | Redis | Live dashboard JSON |
| `GET /api/v1/alerts` | Redis | Danh sách alert đang active |
| `GET /api/v1/alerts/{alert_id}/clip` | S3 presigned | Redirect đến video clip |
| `GET /api/v1/alerts/{alert_id}/snapshot` | S3 presigned | Redirect đến ảnh snapshot |
| `POST /api/v1/alerts/{alert_id}/ack` | Redis | Acknowledge alert |
| `GET /api/v1/analytics/dashboard` | Trino + Redis cache | Historical analytics |
| `GET /api/v1/analytics/alerts` | Trino + Redis cache | Alert analytics |
| `GET /media/live/{camera_id}/snapshot.jpg` | Redis | Latest annotated JPEG |
| `GET /media/live/{camera_id}/stream` | Redis streaming | MJPEG stream |
| `POST /media/live/{camera_id}/webrtc/offer` | — | WebRTC offer/answer |

## 3. Live Dashboard Data (`/api/v1/live/{camera_id}/dashboard`)

**Đọc từ Redis:**

```json
{
  "store": {"store_id": "store_001", "name": "Store 001"},
  "camera": {"camera_id": "cam_01", "status": "online"},
  "frame": {
    "frame_index": 1200,
    "capture_ts": "2026-06-23T15:00:00Z",
    "detection_count": 8,
    "metadata_status": "fresh",
    "latency_ms": 185
  },
  "media": {
    "media_latency_ms": 110,
    "media_status": "online",
    "media_fps": 15
  },
  "occupancy": {
    "current_count": 22,
    "active_track_count": 18
  },
  "heatmap": [...],
  "zone_occupancy": [
    {"zone_id": "checkout_queue_01", "count": 3, "zone_type": "queue"}
  ],
  "queue_status": [
    {"zone_id": "checkout_queue_03", "avg_wait_ms": 125000, "max_wait_ms": 128000}
  ],
  "alerts": [
    {
      "alert_id": "cam_01_checkout_queue_03_long_wait_1782220386558",
      "alert_type": "long_wait",
      "severity": "medium",
      "title": "Long wait — checkout queue 03",
      "description": "Max 2m 05s, avg 2m 05s",
      "status": "new"
    }
  ]
}
```

**Freshness indicators:**
- `metadata_status`: `fresh` (<1500ms), `lagging` (<5000ms), `stale` (>5000ms)
- `media_status`: `online` (<3000ms), `warning` (>3000ms)

## 4. Analytics Dashboard (`/api/v1/analytics/dashboard`)

**Source:** Trino SQL query → Gold Serving Iceberg tables

**Redis cache:** TTL 5 phút — lần đầu gọi ~2.3s (Trino cold), các lần sau ~60ms (cache hit).

**Response chứa:**
```json
{
  "summary": {
    "total_visitors": 5816,
    "total_detections": 363295,
    "active_days": 1,
    "peak_hour": "15:00",
    "avg_dwell_sec": 18.2
  },
  "visitors_series": [{"date": "2026-06-21", "visitors": 5816}],
  "dwell_bands": {"short": 4948, "medium": 718, "long": 150},
  "peak_day": {"date": "2026-06-21", "visitors": 5816, "peak_hour": "15:00"},
  "zone_distribution": [...],
  "alerts_summary": {...}
}
```

**Queries được thực thi (từ `analytics_queries.py`):**
1. `summary_sql()` — JOIN traffic_daily + dwell_daily + queue_daily + alert_daily
2. `visitors_series_sql()` — series theo ngày từ dwell_daily.track_count
3. `dwell_bands_sql()` — short/medium/long counts từ dwell_daily
4. `peak_day_sql()` — ngày có nhiều visitors nhất
5. `zone_hourly_sql()` — phân bố zone theo giờ
6. `alerts_sql()` — alert counts và avg_wait từ alert_daily + queue_daily

## 5. Alert Evaluator (Background Service)

**File:** `services/api/src/rva_api/alert_evaluator.py`

**Chạy:** Background asyncio task, khởi động cùng FastAPI lifespan, check mỗi 10 giây.

**Các check được thực hiện:**

```python
_check_pipeline_lag(client, cam, lag_sec=15, cooldown=30)
    # Đọc live:frame:{cam} → check capture_ts age
    # Nếu > 15 giây → emit pipeline_lag alert

_check_queue_zones(client, cam, overcrowded=5, long_wait_ms=120000, cooldown=30)
    # Đọc queue:live:{cam}:* và zone:count:{cam}
    # count >= 5 → emit queue_overcrowded alert
    # max_wait_ms > 120000 → emit long_wait alert
```

**Alert storage (Redis):**
```
alert:item:{alert_id}     HASH  — chi tiết alert, TTL 24h
alert:live:{cam}          ZSET  — alert IDs theo score=timestamp, max 25 items
alert:cooldown:{...}      STRING — NX EX = cooldown_sec (chống duplicate)
```

**Media consumer thread:** subscribe Pulsar `media-events` → nhận `clip_created` → ghi clip alert vào Redis.

## 6. Live Media Serving

**Transport:** Redis (trong môi trường production demo)

Vision ghi annotated JPEG → `live:frame:bytes:{cam}` (Redis BYTES, TTL 10s)

FastAPI đọc → serve:
- `snapshot.jpg`: trả 1 JPEG
- `stream`: multipart/x-mixed-replace MJPEG stream (polling Redis liên tục)

## 7. React Frontend

**Vị trí code:** `frontend/src/`

**Cấu trúc features:**
```
frontend/src/features/
├── live/           ← Live Monitor page
│   ├── LiveMonitor.tsx
│   ├── LiveVideoPlayer.tsx   ← MJPEG/WebRTC stream
│   ├── ActiveAlerts.tsx      ← Alert panel, realtime
│   ├── QueueStatus.tsx
│   └── ZoneOccupancy.tsx
│
├── analytics/      ← Analytics page
│   ├── AnalyticsDashboard.tsx
│   ├── VisitorsTrend.tsx
│   ├── DwellDistribution.tsx
│   └── AlertsHistory.tsx
│
├── heatmap/        ← Heatmap page
│   └── HeatmapView.tsx
│
└── system/         ← System page
    └── SystemStatus.tsx
```

**API polling:** Live page poll `/api/v1/live/{cam}/dashboard` mỗi 2-3 giây.

**Camera selector:** dropdown chọn camera → thay đổi `camera_id` param → tất cả panels cập nhật.

**Lưu ý quan trọng:** "Active Alerts" chỉ hiển thị alerts của **camera đang được chọn**. Để xem alerts của cam_01, phải chọn Cam_1 trong dropdown.

## 8. Nginx Configuration

```
[Browser] → http://52.74.215.164 → Nginx (:80)
    ├── /api/v1/* → proxy_pass http://api:8000
    ├── /media/*  → proxy_pass http://api:8000
    └── /*        → serve frontend/dist/ (static files)
```

CORS được cấu hình qua env: `CORS_ORIGINS=http://52.74.215.164`
