# Dashboard And Serving

## 1. Mục tiêu

Serving layer biến dữ liệu trong Redis, PostgreSQL, S3 và Iceberg thành API và dashboard cho người dùng. Layer này không xử lý analytics nặng trực tiếp trên raw data; nó gọi đúng storage theo từng use case.

## 2. Thành phần

| Thành phần | Vai trò |
|---|---|
| FastAPI | REST API, WebSocket, MJPEG stream, service integration |
| Streamlit | Live monitor, alert panel, track replay, event search |
| Grafana | Historical KPI, system health, pipeline metrics |
| Trino | SQL backend cho historical analytics |
| Redis | Live serving state |
| PostgreSQL | Operational metadata |
| S3 | Pre-signed URL cho sampled frames |

## 3. Persona và dashboard

| Persona | Dashboard chính | Nhu cầu |
|---|---|---|
| Store manager | Grafana KPI | Traffic theo giờ/ngày, peak time |
| Security/operations | Streamlit Live Monitor | Camera live, heatmap, alert |
| Data analyst | Trino/Grafana/Export | Query lịch sử, so sánh camera |
| System operator | Grafana Ops | Lag, FPS, checkpoint, service health |

## 4. FastAPI responsibilities

FastAPI là serving gateway, không để Streamlit truy cập trực tiếp quá nhiều storage.

Responsibilities:

- Đọc Redis cho live stats.
- Đọc PostgreSQL cho alerts và track metadata.
- Tạo S3 pre-signed URL cho sampled frame.
- Query Trino cho historical metrics.
- Cung cấp WebSocket hoặc Server-Sent Events cho live updates.
- Cung cấp MJPEG endpoint nếu cần video stream mượt hơn Streamlit polling.

## 5. API endpoints

### 5.1 Health

```text
GET /health
GET /api/v1/health/dependencies
```

Response:

```json
{
  "status": "ok",
  "dependencies": {
    "redis": "ok",
    "postgres": "ok",
    "trino": "ok"
  }
}
```

### 5.2 Cameras

```text
GET /api/v1/cameras
GET /api/v1/cameras/{camera_id}
GET /api/v1/cameras/{camera_id}/health
```

### 5.3 Live stats

```text
GET /api/v1/live/{camera_id}/stats
GET /api/v1/live/{camera_id}/heatmap
GET /api/v1/live/{camera_id}/tracks
GET /api/v1/live/alerts
```

Example:

```json
{
  "camera_id": "cam_01",
  "current_count": 15,
  "fps": 24.8,
  "active_tracks": 13,
  "last_frame_ts": "2026-05-05T10:30:00.123Z"
}
```

### 5.4 Alerts

```text
GET /api/v1/alerts?status=active&camera_id=cam_01
POST /api/v1/alerts/{alert_id}/ack
POST /api/v1/alerts/{alert_id}/resolve
```

### 5.5 Tracks

```text
GET /api/v1/tracks/{camera_id}/{track_id}
GET /api/v1/tracks/search?camera_id=cam_01&start=...&end=...
```

### 5.6 Frames

```text
GET /api/v1/frames/signed-url?uri=s3://...
GET /api/v1/stream/{camera_id}/mjpeg
```

### 5.7 Historical analytics

```text
GET /api/v1/analytics/hourly-traffic?store_id=...&date=...
GET /api/v1/analytics/camera-minute?camera_id=...&start=...&end=...
GET /api/v1/analytics/heatmap-hourly?camera_id=...&date=...
```

## 6. WebSocket messages

Endpoint:

```text
WS /api/v1/ws/live/{camera_id}
```

Message types:

```json
{"type": "stats", "camera_id": "cam_01", "count": 15, "fps": 24.8}
{"type": "heatmap", "camera_id": "cam_01", "cells": [{"x": 32, "y": 18, "v": 12.5}]}
{"type": "alert", "alert_id": "alert-...", "severity": "medium"}
{"type": "camera_health", "camera_id": "cam_01", "status": "online"}
```

## 7. Streamlit pages

### 7.1 Live Monitor

Primary page.

Features:

- Select store/camera.
- Show latest frame or MJPEG stream.
- Overlay heatmap on frame.
- Toggle bounding boxes.
- Show current count, FPS, active tracks.
- Show active alerts.
- Show camera health.

Data source:

- API live stats endpoint.
- API heatmap endpoint.
- API frame/MJPEG endpoint.

### 7.2 Alerts

Features:

- Active alert list.
- Acknowledge alert.
- Resolve alert.
- View alert details and snapshot frame.
- Filter by camera, severity, time.

Data source:

- PostgreSQL via API.
- S3 pre-signed frame URL via API.

### 7.3 Track Replay

Features:

- Search track by camera/time/track_id.
- Show first/last seen, duration.
- Show sampled path over frame.
- Show position samples.

Data source:

- PostgreSQL track events.
- Sampled frames from S3.

### 7.4 Historical Analytics

Features:

- Hourly traffic.
- Daily comparison.
- Historical heatmap by hour.
- Top cameras by peak count.

Data source:

- Trino/Iceberg via API.

## 8. Grafana dashboards

### 8.1 Retail KPI dashboard

| Panel | Data source |
|---|---|
| Visitors today estimate | Trino Gold |
| Peak hour | Trino Gold |
| Hourly person count | Trino Gold |
| Camera comparison | Trino Gold |
| Historical heatmap summary | Trino Gold |

### 8.2 Realtime operations dashboard

| Panel | Data source |
|---|---|
| Current count by camera | Redis exporter or API metrics |
| Active alerts | PostgreSQL/API |
| Camera online status | PostgreSQL/Prometheus |
| Processing FPS | Prometheus |

### 8.3 Pipeline health dashboard

| Panel | Data source |
|---|---|
| Pulsar publish/consume rate | Prometheus |
| Consumer lag | Pulsar metrics |
| Flink checkpoint duration | Flink metrics |
| Flink restart count | Flink metrics |
| Redis memory | Redis exporter |
| PostgreSQL connections | Postgres exporter |
| API latency | Prometheus |

## 9. Streamlit realtime limitation

Streamlit không phải frontend realtime tối ưu cho video FPS cao. Thiết kế demo nên chọn một trong hai hướng:

| Hướng | Khi dùng |
|---|---|
| Polling 1 FPS | Demo đơn giản, live heatmap không cần video mượt |
| MJPEG endpoint | Cần stream frame mượt hơn trong browser |
| streamlit-webrtc | Cần WebRTC interaction, setup phức tạp hơn |
| React frontend | Production direction, ngoài phạm vi MVP |

Đề xuất MVP:

- Streamlit dùng polling/API để hiển thị heatmap và latest frame.
- FastAPI cung cấp MJPEG endpoint nếu cần live frame mượt hơn.

## 10. Security

- Không trả trực tiếp S3 private URI cho browser nếu bucket private.
- API tạo pre-signed URL có thời hạn ngắn.
- RTSP URL không hiển thị trên dashboard.
- Dashboard auth có thể đơn giản trong MVP nhưng cần nêu hướng production.
- Không hiển thị hoặc lưu PII.

## 11. Success criteria

- Streamlit xem được live count và heatmap.
- Alert mới xuất hiện trên dashboard trong vài giây.
- Có thể search alert/track và mở sampled frame.
- Grafana query được Gold tables qua Trino.
- Ops dashboard thể hiện FPS, lag, checkpoint hoặc health.

