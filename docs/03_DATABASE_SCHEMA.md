# Database Schema

## Overview

The system uses two databases:
- **PostgreSQL**: Stores **important events** (track start/end, alerts, sampled positions) — raw 30 FPS detections are NOT stored here
- **Redis**: Real-time state, heatmap grid, WebSocket pub/sub

### Design Principle

| Feature | Status | Description |
|---------|--------|-------------|
| **Heatmap** | Primary | Density visualization directly from bbox coordinates |
| **Zone** | Removed | Not needed — heatmap provides full spatial information |

### PostgreSQL Write Strategy

```
Raw detections (30 FPS) → Iceberg Bronze layer only

PostgreSQL receives only:
  - Track start: when a new track_id appears for the first time
  - Track end:   when a track_id loses signal for > 30 seconds
  - Position sample: once per second (not 30 times per second)
  - Alerts:      when density exceeds threshold

Result: ~3,600 events/hour/camera (vs 108,000 raw detections)
```

---

## 1. PostgreSQL Schema

### 1.1 Database Setup

```sql
CREATE DATABASE rva_metadata;

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS system;

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### 1.2 Core Tables

#### cameras

```sql
CREATE TABLE core.cameras (
    camera_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    location VARCHAR(200),
    store_id VARCHAR(50),

    -- Technical info
    rtsp_url VARCHAR(500),
    resolution VARCHAR(20),  -- "1920x1080"
    fps INTEGER DEFAULT 30,

    -- Heatmap config
    heatmap_grid_width INTEGER DEFAULT 64,
    heatmap_grid_height INTEGER DEFAULT 48,
    heatmap_decay_rate FLOAT DEFAULT 0.95,

    -- Status
    status VARCHAR(20) DEFAULT 'active',
    last_seen TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### track_events — Track lifecycle events (Primary)

```sql
-- Stores track_start/track_end events and sampled positions only
-- Raw detections (30 FPS) go to Iceberg Bronze layer
CREATE TABLE core.track_events (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    camera_id VARCHAR(50) NOT NULL REFERENCES core.cameras(camera_id),
    track_id INTEGER NOT NULL,
    event_type VARCHAR(20) NOT NULL,  -- 'track_start', 'track_end', 'position_sample'

    timestamp TIMESTAMPTZ NOT NULL,

    -- Position at time of event
    center_x SMALLINT,
    center_y SMALLINT,
    confidence FLOAT,

    -- Media (for track_start and track_end only)
    frame_path VARCHAR(500),

    created_at TIMESTAMPTZ DEFAULT NOW()
) PARTITION BY RANGE (timestamp);

-- Monthly partitions
CREATE TABLE track_events_2024_03
    PARTITION OF core.track_events
    FOR VALUES FROM ('2024-03-01') TO ('2024-04-01');

CREATE TABLE track_events_2024_04
    PARTITION OF core.track_events
    FOR VALUES FROM ('2024-04-01') TO ('2024-05-01');

-- Indexes
CREATE INDEX idx_track_events_camera_time
    ON core.track_events(camera_id, timestamp DESC);
CREATE INDEX idx_track_events_track
    ON core.track_events(track_id, camera_id);
```

#### tracks — Track summary (one row per visitor)

```sql
CREATE TABLE core.tracks (
    id SERIAL PRIMARY KEY,
    track_id INTEGER NOT NULL,
    camera_id VARCHAR(50) NOT NULL REFERENCES core.cameras(camera_id),

    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,

    -- Sampled path: 1 point/second (not every frame)
    -- 1 hour = ~3,600 points (vs 108,000 if stored at 30 FPS)
    path JSONB NOT NULL,  -- [{"x": 125, "y": 260, "t": "2024-03-28T14:30:00Z"}, ...]

    total_duration_seconds INTEGER,
    frame_path_start VARCHAR(500),  -- Frame at first appearance
    frame_path_end VARCHAR(500),    -- Frame at disappearance

    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(track_id, camera_id, first_seen)
);
```

#### heatmap_snapshots — Historical heatmap storage

```sql
CREATE TABLE analytics.heatmap_snapshots (
    id SERIAL PRIMARY KEY,
    camera_id VARCHAR(50) NOT NULL REFERENCES core.cameras(camera_id),

    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    granularity VARCHAR(20) NOT NULL,  -- 'minute', 'hour', 'day'

    grid_width INTEGER NOT NULL,
    grid_height INTEGER NOT NULL,
    heatmap_data JSONB NOT NULL,  -- Sparse format: [{"x":10,"y":20,"v":150}, ...]

    total_detections INTEGER,
    max_density INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(camera_id, start_time, granularity)
);
```

#### alerts

```sql
CREATE TABLE core.alerts (
    alert_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    alert_type VARCHAR(50) NOT NULL,  -- 'crowd', 'density_spike', 'camera_offline'
    severity VARCHAR(20) DEFAULT 'medium',

    camera_id VARCHAR(50) REFERENCES core.cameras(camera_id),

    -- Location (grid coordinates from heatmap)
    hotspot_x INTEGER,
    hotspot_y INTEGER,

    triggered_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,

    details JSONB,
    snapshot_path VARCHAR(500),

    status VARCHAR(20) DEFAULT 'active',

    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 1.3 Analytics Tables

```sql
-- Hourly aggregations
CREATE TABLE analytics.hourly_stats (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    hour INTEGER NOT NULL,
    camera_id VARCHAR(50) NOT NULL,

    total_detections INTEGER,
    unique_tracks INTEGER,
    max_concurrent INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(date, hour, camera_id)
);

-- Daily summaries
CREATE TABLE analytics.daily_stats (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    store_id VARCHAR(50) NOT NULL,

    total_visitors INTEGER,
    peak_hour INTEGER,
    peak_count INTEGER,
    hotspot_areas JSONB,

    prev_day_change_pct FLOAT,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(date, store_id)
);
```

### 1.4 System Tables

```sql
CREATE TABLE system.feature_flags (
    flag_name VARCHAR(50) PRIMARY KEY,
    enabled BOOLEAN DEFAULT FALSE,
    config JSONB,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Heatmap and alerts enabled by default
INSERT INTO system.feature_flags (flag_name, enabled, config) VALUES
    ('heatmap_enabled', TRUE, '{"decay_rate": 0.95, "grid_size": 30, "decay_interval_sec": 3}'),
    ('alerts_enabled', TRUE, '{"density_threshold": 30, "crowd_threshold": 20}');
```

---

## 2. Redis Schema

### 2.1 Live Heatmap (Primary)

```redis
# Sorted Set: grid cells with density scores
# Key: heatmap:live:{camera_id}

# Add/increment detection point
ZINCRBY heatmap:live:cam_01 1 "32,24"

# Get top 20 hotspots
ZREVRANGE heatmap:live:cam_01 0 19 WITHSCORES

# Get all data for rendering
ZRANGE heatmap:live:cam_01 0 -1 WITHSCORES
```

### 2.2 Real-time Statistics

```redis
# Current person count
SET stats:count:cam_01 15 EX 5

# Detection rate per minute
INCR stats:detections:cam_01:minute
EXPIRE stats:detections:cam_01:minute 60

# Unique tracks (HyperLogLog)
PFADD stats:tracks:cam_01:hour 42 43 44
PFCOUNT stats:tracks:cam_01:hour
```

### 2.3 Active Tracks

```redis
HSET track:active:42 \
    camera_id "cam_01" \
    last_x 150 \
    last_y 200 \
    last_seen "2024-03-28T14:30:05Z"

EXPIRE track:active:42 30
```

### 2.4 Alert Queue

```redis
LPUSH alert:queue '{"type":"density_spike","camera_id":"cam_01","hotspot":{"x":32,"y":24},"density":45}'

LRANGE alert:queue 0 9
```

### 2.5 Pub/Sub Channels

```redis
# Detection events
PUBLISH channel:detections '{"camera_id":"cam_01","track_id":42,"x":150,"y":200}'

# Heatmap updates (every 100ms)
PUBLISH channel:heatmap '{"camera_id":"cam_01","hotspots":[{"x":32,"y":24,"v":45}]}'

# Stats
PUBLISH channel:stats '{"cam_01":{"count":15,"fps":28}}'

# Alerts
PUBLISH channel:alerts '{"type":"density_spike","camera_id":"cam_01"}'
```

---

## 3. Data Flow

### 3.1 Heatmap Processing (Primary)

```python
async def process_detection(detection):
    camera_id = detection['camera_id']
    bbox = detection['bbox']

    # Calculate center
    cx = int(bbox['x'] + bbox['w'] / 2)
    cy = int(bbox['y'] + bbox['h'] / 2)

    # Convert to grid cell
    grid_x = cx // 30
    grid_y = cy // 30
    cell_key = f"{grid_x},{grid_y}"

    # Update heatmap
    redis.zincrby(f"heatmap:live:{camera_id}", 1, cell_key)

    # Update track
    redis.hset(f"track:active:{detection['track_id']}", mapping={
        "camera_id": camera_id,
        "last_x": cx,
        "last_y": cy
    })
    redis.expire(f"track:active:{detection['track_id']}", 30)

    # Publish to WebSocket
    redis.publish("channel:detections", json.dumps({
        "camera_id": camera_id,
        "x": cx,
        "y": cy
    }))

    # Write to PostgreSQL — only for position_sample (once per second)
    # track_start and track_end are written by TrackLifecycleManager
    if should_sample(detection['timestamp']):  # every 1 second
        await db.execute("""
            INSERT INTO core.track_events
            (camera_id, track_id, event_type, timestamp, center_x, center_y, confidence)
            VALUES ($1, $2, 'position_sample', $3, $4, $5, $6)
        """, camera_id, detection['track_id'],
            detection['timestamp'], cx, cy, detection['confidence'])
```

### 3.2 Heatmap Decay

```python
# Runs every 3 seconds (NOT every frame)
# If decay ran every second at rate=0.95: after 60s = 0.95^60 ≈ 0.05 → blank heatmap
# If decay runs every 3 seconds at rate=0.95: after 60s = 0.95^20 ≈ 0.36 → natural fade
async def apply_decay(camera_id, decay_rate=0.95):
    # Schedule: asyncio.create_task + sleep(3) or APScheduler interval=3s
    cells = redis.zrange(f"heatmap:live:{camera_id}", 0, -1, withscores=True)

    pipe = redis.pipeline()
    for cell, score in cells:
        new_score = score * decay_rate
        if new_score < 0.1:
            pipe.zrem(f"heatmap:live:{camera_id}", cell)
        else:
            pipe.zadd(f"heatmap:live:{camera_id}", {cell: new_score})
    pipe.execute()
```

---

## 4. Configuration

```python
# config.py
class Config:
    # Heatmap
    HEATMAP_GRID_WIDTH = 64       # 64 columns
    HEATMAP_GRID_HEIGHT = 48      # 48 rows
    HEATMAP_DECAY_RATE = 0.95     # 5% reduction per decay cycle
    HEATMAP_CELL_SIZE = 30        # pixels per cell
    HEATMAP_DECAY_INTERVAL = 3    # seconds: decay runs every 3 seconds

    # PostgreSQL sampling
    TRACK_POSITION_SAMPLE_INTERVAL = 1  # seconds: write position every 1 second

    # Alerting thresholds
    CROWD_THRESHOLD = 20    # people: alert when >= 20 people within 5 seconds
    DENSITY_THRESHOLD = 30  # people: density spike alert when >= 30 people/30 seconds
```

---

## Related Documents

- [02_ARCHITECTURE_IMPROVED.md](./02_ARCHITECTURE_IMPROVED.md) - Dual-Path architecture
- [04_VISUALIZATION_REQUIREMENTS.md](./04_VISUALIZATION_REQUIREMENTS.md) - Visualization specifications
