# Operational Storage

## 1. Mục tiêu

Operational storage phục vụ ứng dụng chạy realtime và tra cứu nhanh. Nó khác lakehouse:

- Redis dùng cho state ngắn hạn, latency thấp.
- PostgreSQL dùng cho metadata nghiệp vụ và event cần tra cứu.
- S3 dùng cho sampled frames.
- Iceberg không nằm trong operational path chính mà phục vụ analytics.

## 2. Phân chia trách nhiệm

| Storage | Dữ liệu | Retention | Access pattern |
|---|---|---:|---|
| Redis | Live count, heatmap, active tracks, alert queue | Giây đến giờ | Read/write rất nhanh |
| PostgreSQL | Cameras, track lifecycle, alert history, configs | Dài hạn | Query theo camera/time/id |
| S3 | Sampled frames, optional clips, Iceberg data files | Ngày đến năm | Object lookup |
| Iceberg | Historical analytical data | Dài hạn | SQL scan/aggregate |

## 3. PostgreSQL schema

### 3.1 Schema namespaces

```sql
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS app;
```

### 3.2 `core.stores`

```sql
CREATE TABLE core.stores (
    store_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    address TEXT,
    timezone VARCHAR(64) DEFAULT 'Asia/Ho_Chi_Minh',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.3 `core.cameras`

```sql
CREATE TABLE core.cameras (
    camera_id VARCHAR(64) PRIMARY KEY,
    store_id VARCHAR(64) NOT NULL REFERENCES core.stores(store_id),
    name VARCHAR(200) NOT NULL,
    location VARCHAR(200),
    rtsp_url TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    fps_target INTEGER DEFAULT 25,
    resolution_width INTEGER,
    resolution_height INTEGER,
    heatmap_grid_width INTEGER DEFAULT 64,
    heatmap_grid_height INTEGER DEFAULT 48,
    status VARCHAR(32) DEFAULT 'unknown',
    last_seen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 3.4 `ops.track_events`

```sql
CREATE TABLE ops.track_events (
    track_event_id VARCHAR(128) PRIMARY KEY,
    store_id VARCHAR(64) NOT NULL,
    camera_id VARCHAR(64) NOT NULL,
    track_id INTEGER NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    event_ts TIMESTAMPTZ NOT NULL,
    x INTEGER,
    y INTEGER,
    confidence DOUBLE PRECISION,
    frame_uri TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT chk_track_event_type
        CHECK (event_type IN ('track_start', 'position_sample', 'track_end'))
);

CREATE INDEX idx_track_events_camera_time
    ON ops.track_events(camera_id, event_ts DESC);

CREATE INDEX idx_track_events_track
    ON ops.track_events(camera_id, track_id, event_ts);
```

### 3.5 `ops.tracks`

Một row tóm tắt một track sau khi kết thúc hoặc được upsert định kỳ.

```sql
CREATE TABLE ops.tracks (
    track_uid VARCHAR(128) PRIMARY KEY,
    store_id VARCHAR(64) NOT NULL,
    camera_id VARCHAR(64) NOT NULL,
    track_id INTEGER NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    duration_seconds INTEGER,
    sample_count INTEGER DEFAULT 0,
    path JSONB,
    frame_uri_start TEXT,
    frame_uri_end TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(camera_id, track_id, first_seen_at)
);
```

### 3.6 `ops.alerts`

```sql
CREATE TABLE ops.alerts (
    alert_id VARCHAR(128) PRIMARY KEY,
    alert_type VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL DEFAULT 'medium',
    store_id VARCHAR(64) NOT NULL,
    camera_id VARCHAR(64),
    event_ts TIMESTAMPTZ NOT NULL,
    window_start TIMESTAMPTZ,
    window_end TIMESTAMPTZ,
    hotspot_grid_x INTEGER,
    hotspot_grid_y INTEGER,
    metrics JSONB,
    status VARCHAR(32) DEFAULT 'active',
    acknowledged_by VARCHAR(128),
    acknowledged_at TIMESTAMPTZ,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alerts_status_time
    ON ops.alerts(status, event_ts DESC);
```

### 3.7 `ops.camera_health`

```sql
CREATE TABLE ops.camera_health (
    camera_id VARCHAR(64) PRIMARY KEY,
    store_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    last_frame_ts TIMESTAMPTZ,
    last_error TEXT,
    fps_observed DOUBLE PRECISION,
    restart_count INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

## 4. PostgreSQL write strategy

Không ghi raw detection 30 FPS vào PostgreSQL.

Ghi vào PostgreSQL:

- Camera config và health.
- Track start/end.
- Position sample mỗi 1 giây hoặc 2 giây.
- Alert events.
- User actions như acknowledge alert.

Không ghi vào PostgreSQL:

- Raw frame detections mỗi frame.
- Full heatmap long-term.
- Large image/video binary.

## 5. Redis key design

### 5.1 Current stats

```redis
SET stats:count:{camera_id} 15 EX 5
SET stats:fps:{camera_id} 24.7 EX 10
SET stats:last_frame_ts:{camera_id} "2026-05-05T10:30:00.123Z" EX 30
```

### 5.2 Live heatmap

```redis
ZINCRBY heatmap:live:{camera_id} 1 "{grid_x},{grid_y}"
ZRANGE heatmap:live:{camera_id} 0 -1 WITHSCORES
ZREVRANGE heatmap:live:{camera_id} 0 20 WITHSCORES
EXPIRE heatmap:live:{camera_id} 60
```

### 5.3 Active tracks

```redis
HSET track:active:{camera_id}:{track_id} \
    x 200 \
    y 410 \
    confidence 0.87 \
    last_seen "2026-05-05T10:30:00Z"
EXPIRE track:active:{camera_id}:{track_id} 30
```

### 5.4 Alert queue

```redis
LPUSH alerts:active '{"alert_id":"...","camera_id":"cam_01"}'
LTRIM alerts:active 0 99
PUBLISH channel:alerts '{"type":"alert","alert_id":"..."}'
```

### 5.5 Pub/sub channels

| Channel | Payload |
|---|---|
| `channel:stats` | Current count, FPS |
| `channel:heatmap` | Updated cells hoặc full sparse grid |
| `channel:alerts` | Alert events |
| `channel:camera-health` | Online/offline status |

## 6. S3 object layout

Sampled frame path:

```text
s3://retail-video-analytics/frames/{event_date}/{store_id}/{camera_id}/{hour}/{HH-mm-ss}_{frame_index}.jpg
```

Ví dụ:

```text
s3://retail-video-analytics/frames/2026-05-05/store_001/cam_01/10/10-30-00_001502.jpg
```

Optional clip path:

```text
s3://retail-video-analytics/clips/{event_date}/{store_id}/{camera_id}/{alert_id}.mp4
```

Iceberg warehouse path:

```text
s3://retail-video-analytics/warehouse/retail_bronze/
s3://retail-video-analytics/warehouse/retail_silver/
s3://retail-video-analytics/warehouse/retail_gold/
```

## 7. Frame retention

| Loại object | Retention demo | Production direction |
|---|---:|---:|
| Sampled frames | 7 ngày | 7 đến 30 ngày |
| Alert snapshots | 30 ngày | 30 đến 90 ngày |
| Iceberg data | Không xóa trong demo | Theo lifecycle của bảng |
| Temporary upload | 1 ngày | 1 ngày |

## 8. API access patterns

### Live monitor

| API cần dữ liệu | Storage |
|---|---|
| Current count | Redis |
| Heatmap live | Redis |
| Active alerts | Redis + PostgreSQL |
| Latest frame | S3 hoặc MJPEG stream |
| Camera health | Redis/PostgreSQL |

### Event investigation

| API cần dữ liệu | Storage |
|---|---|
| Search alerts | PostgreSQL |
| Load track lifecycle | PostgreSQL |
| Load sampled frame | S3 pre-signed URL |
| Historical metrics | Trino/Iceberg |

## 9. Consistency model

| Dữ liệu | Model |
|---|---|
| Live count | Eventually consistent, TTL ngắn |
| Live heatmap | Eventually consistent, decay theo thời gian |
| Alert history | Idempotent insert vào PostgreSQL |
| Track lifecycle | Idempotent insert/upsert |
| Historical aggregate | Iceberg snapshot consistency |

## 10. Operational storage success criteria

- Redis có thể trả live heatmap trong dưới 500 ms ở demo.
- PostgreSQL không bị dùng làm raw event store.
- Track và alert có unique key để chống duplicate.
- S3 path nhất quán và tra cứu được từ event.
- API có thể lấy dữ liệu live từ Redis và lịch sử từ PostgreSQL/Trino.

