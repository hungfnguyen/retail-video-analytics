# Dual-Path Architecture

## Overview

RVA uses a **Dual-Path Architecture** combining:
- **Fast Path**: Real-time alerting (< 1 second) → Redis + WebSocket
- **Slow Path**: Historical analytics (90-120 seconds) → Iceberg + Trino + Grafana

---

## 1. Architecture Diagram

```
                              ┌─────────────────────────────────────┐
                              │           EDGE LAYER                │
                              │  ┌─────────────────────────────┐    │
                              │  │   Camera 1..N (RTSP)        │    │
                              │  └──────────────┬──────────────┘    │
                              │                 │                   │
                              │  ┌──────────────▼──────────────┐    │
                              │  │   YOLO11 + BoTSORT          │    │
                              │  │   (Detection + Tracking)    │    │
                              │  └──────────────┬──────────────┘    │
                              │                 │                   │
                              │         JSON + Frames               │
                              └─────────────────┼───────────────────┘
                                                │
                    ┌───────────────────────────┼───────────────────────────┐
                    │                           │                           │
                    ▼                           ▼                           ▼
          ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
          │  Apache Pulsar  │         │   GCS (S3)    │         │   PostgreSQL    │
          │  (Metadata)     │         │   (Frames)      │         │   (Events)      │
          └────────┬────────┘         └─────────────────┘         └─────────────────┘
                   │
       ┌───────────┴───────────┐
       │                       │
       ▼                       ▼
┌──────────────┐       ┌──────────────┐
│  FAST PATH   │       │  SLOW PATH   │
│   < 1 sec    │       │   1-5 min    │
└──────┬───────┘       └──────┬───────┘
       │                      │
       ▼                      ▼
┌──────────────┐       ┌──────────────┐
│ Flink CEP    │       │ Flink Batch  │
│ (Alerting)   │       │ (Medallion)  │
└──────┬───────┘       └──────┬───────┘
       │                      │
       ▼                      ▼
┌──────────────┐       ┌──────────────┐
│    Redis     │       │   Iceberg    │
│  (State)     │       │  (B→S→G)     │
└──────┬───────┘       └──────┬───────┘
       │                      │
       ▼                      ▼
┌──────────────┐       ┌──────────────┐
│  WebSocket   │       │    Trino     │
│  (Streaming) │       │  (Analytics) │
└──────┬───────┘       └──────┬───────┘
       │                      │
       └──────────┬───────────┘
                  │
                  ▼
       ┌──────────────────────────────────────────┐
       │           PRESENTATION LAYER             │
       ├──────────────┬──────────────┬────────────┤
       │  Streamlit   │   Grafana    │  REST API  │
       │  (Real-time) │  (Analytics) │ (Integr.)  │
       └──────────────┴──────────────┴────────────┘
```

---

## 2. Layer Details

### 2.1 Edge Layer

**Components:**
- Cameras: IP cameras with RTSP stream
- Vision Processing: YOLO11 + BoTSORT

**Output:**
```json
{
  "camera_id": "cam_01",
  "timestamp": "2024-03-28T14:30:00.123Z",
  "frame_id": "frame_001",
  "detections": [
    {
      "track_id": 42,
      "class": "person",
      "confidence": 0.92,
      "bbox": {"x": 100, "y": 200, "w": 50, "h": 120},
      "center_x": 125,
      "center_y": 260
    }
  ]
}
```

**Frame Output:**
- Format: JPEG
- Path: `gs://frames/{date}/{camera_id}/{hour}/{frame_id}.jpg`
- Retention: 7 days

### 2.2 Ingestion Layer

| Component | Purpose | Data Type |
|-----------|---------|-----------|
| **Pulsar** | Stream detection metadata | JSON |
| **GCS** | Store frames and clips | JPEG/MP4 |
| **PostgreSQL** | Store event metadata | Structured |

**Pulsar Topics:**
```
persistent://retail/metadata/events      # Raw detections
persistent://retail/alerts/density       # Density spike alerts
persistent://retail/metrics/system       # System health metrics
```

### 2.3 Fast Path (Real-time)

**Purpose**: Alerting with latency < 1 second

**Flow:**
```
Pulsar → Flink CEP → Redis → WebSocket → UI
```

**Flink CEP Rules (Density-Based):**

```java
// Crowd Detection Rule
// Counts detections across the entire frame within a time window
Pattern<Detection, ?> crowdPattern = Pattern
    .<Detection>begin("crowd_start")
    .where(new SimpleCondition<Detection>() {
        @Override
        public boolean filter(Detection event) {
            return event.getObjectClass().equals("person")
                && event.getConfidence() >= 0.4;
        }
    })
    .timesOrMore(CROWD_THRESHOLD)  // e.g., >= 20 people
    .within(Time.seconds(5));

// Density Spike: sudden increase in density within 30 seconds
Pattern<Detection, ?> densitySpikePattern = Pattern
    .<Detection>begin("spike")
    .where(new SimpleCondition<Detection>() {
        @Override
        public boolean filter(Detection event) {
            return event.getObjectClass().equals("person");
        }
    })
    .timesOrMore(SPIKE_THRESHOLD)  // e.g., >= 30 people
    .within(Time.seconds(30));
```

**Note**: Alerting is based on **full-frame density**, no zones required.
Redis stores the heatmap grid to identify **which area** is most crowded.

**Redis Data Structures:**

```redis
# Live heatmap grid (SORTED SET) — primary data store
ZINCRBY heatmap:live:cam_01 1 "32,24"   # grid cell (col,row)

# Current person count (STRING with TTL)
SET stats:count:cam_01 15 EX 5

# Unique tracks per hour (HyperLogLog)
PFADD stats:tracks:cam_01:hour 42 43 44
PFCOUNT stats:tracks:cam_01:hour

# Active tracks (HASH with TTL)
HSET track:active:42 camera_id "cam_01" last_x 125 last_y 260 last_seen "..."
EXPIRE track:active:42 30

# Alerts queue (LIST)
LPUSH alert:queue '{"type":"density_spike","camera_id":"cam_01","count":25,"timestamp":"..."}'

# Pub/Sub channels
PUBLISH channel:heatmap '{"camera_id":"cam_01","hotspots":[{"x":32,"y":24,"v":45}]}'
PUBLISH channel:stats '{"cam_01":{"count":15,"fps":28}}'
PUBLISH channel:alerts '{"type":"density_spike","camera_id":"cam_01","count":25}'
```

### 2.4 Slow Path (Analytics)

**Purpose**: Historical analytics with high accuracy

**Flow:**
```
Pulsar → Flink Batch → Iceberg (Bronze→Silver→Gold) → Trino → Grafana
```

**Actual latency**: 90-120 seconds (bounded by Flink checkpoint interval 30-60s)
Suitable for: hourly/daily reports, trend analysis, historical heatmaps.

**Medallion Layers:**

| Layer | Table | Description | Retention |
|-------|-------|-------------|-----------|
| Bronze | `bronze_raw` | Raw detections from Pulsar | 30 days |
| Silver | `silver_detections` | Deduplicated, confidence >= 0.4 | 90 days |
| Gold | `gold_minute_by_cam` | Aggregated per minute per camera | 1 year |
| Gold | `gold_hour_by_cam` | Aggregated per hour per camera | 2 years |
| Gold | `gold_heatmap_snapshot` | Hourly heatmap snapshots | 1 year |
| Gold | `gold_track_summary` | Track journey summaries | 90 days |

### 2.5 Query Layer

**Trino** for batch analytics:
```sql
-- Daily traffic comparison (by camera, by hour)
SELECT
    date,
    camera_id,
    hour,
    unique_tracks,
    max_concurrent
FROM gold_hour_by_cam
WHERE date >= CURRENT_DATE - INTERVAL '7' DAY
ORDER BY date, hour;

-- Heatmap snapshot (historical hotspots)
SELECT camera_id, start_time, heatmap_data
FROM gold_heatmap_snapshot
WHERE camera_id = 'cam_01'
  AND start_time >= CURRENT_TIMESTAMP - INTERVAL '1' DAY;
```

**Redis** for real-time:
```python
# Get live heatmap grid
heatmap = redis.zrevrange("heatmap:live:cam_01", 0, -1, withscores=True)

# Get current person count
count = redis.get("stats:count:cam_01")

# Get active alerts
alerts = redis.lrange("alert:queue", 0, 9)
```

### 2.6 Presentation Layer

| Tool | Purpose | Data Source | Users |
|------|---------|-------------|-------|
| **Streamlit** | Real-time monitoring, video, heatmap | Redis, WebSocket, GCS | Security, Analyst |
| **Grafana** | Time-series analytics, system health | Trino, Prometheus | Manager, IT |
| **REST API** | Integration, mobile apps | PostgreSQL, GCS | External systems |

---

## 3. Data Flow Diagrams

### 3.1 Real-time Alert Flow

```
Camera → YOLO → Pulsar → Flink CEP → Redis → WebSocket → Streamlit UI
                                        ↓
                                   PostgreSQL
                                   (event log)
```

**Latency Budget:**
| Step | Max Latency |
|------|-------------|
| YOLO inference | 50ms |
| Pulsar publish | 10ms |
| Flink CEP | 100ms |
| Redis write | 5ms |
| WebSocket push | 50ms |
| **Total** | **< 300ms** |

### 3.2 Analytics Flow

```
Camera → YOLO → Pulsar → Flink Batch → Iceberg Bronze
                              ↓
                         Iceberg Silver (every 1 min)
                              ↓
                         Iceberg Gold (every 5 min)
                              ↓
                            Trino
                              ↓
                           Grafana
```

**Actual Latency Budget:**
| Step | Max Latency | Reason |
|------|-------------|--------|
| Bronze ingestion | 30-60s | Flink checkpoint interval |
| Silver transformation | 30-60s | Separate job, separate checkpoint |
| Gold aggregation | 30-60s | Separate job, separate checkpoint |
| Trino query | 2-5s | Iceberg snapshot scan |
| **Total** | **90-180s** | **~2-3 minutes worst case** |

### 3.3 Media Lookup Flow

```
User Request → REST API → PostgreSQL (find event)
                              ↓
                         Get frame_path
                              ↓
                         GCS (fetch frame)
                              ↓
                         Return to UI
```

---

## 4. Scalability

### Horizontal Scaling

| Component | Scaling Method |
|-----------|----------------|
| Cameras | Add more camera feeds |
| YOLO | Multiple GPU workers |
| Pulsar | Add brokers, partitions |
| Flink | Increase parallelism |
| Redis | Redis Cluster |
| GCS | Add nodes |
| PostgreSQL | Read replicas |

### Camera Scaling Formula

```
Resources per camera:
- YOLO: 0.5 GPU core @ 30 FPS
- Pulsar: 100 msg/sec @ 1KB each
- GCS: 100KB/frame × 1 frame/sec = 100 KB/sec (keyframes only)
- PostgreSQL: ~1 event/sec (sampled)

For 100 cameras:
- GPU: 50 cores (e.g., 5× RTX 4090)
- Pulsar: 10,000 msg/sec
- GCS: 10 MB/sec
- PostgreSQL: 100 events/sec
```

---

## 5. Future Considerations (Production Scale)

| Component | Current (Project) | Future (Production) |
|-----------|-----------------|---------------------|
| Redis | Single node | Redis Cluster |
| PostgreSQL | Single instance | Read replicas + partitioning |
| GCS | Single node | Multi-node erasure coding |
| Flink | Single job | Multiple jobs, higher parallelism |
| Cameras | 1-2 cameras | 10-100 cameras with edge GPU |

---

## 6. Docker Compose Services

```yaml
services:
  # Existing services
  pulsar:
    image: apachepulsar/pulsar:3.3.2

  flink-jobmanager:
    image: flink:1.18

  flink-taskmanager:
    image: flink:1.18

  trino:
    image: trinodb/trino:418

  grafana:
    image: grafana/grafana:11.3.0

  # Fast Path: Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  # Metadata database
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: rva_metadata
      POSTGRES_USER: rva
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    ports:
      - "5432:5432"

  # WebSocket + REST API server
  backend:
    build: ./backend
    container_name: rva-backend
    ports:
      - "8000:8000"
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
    environment:
      - REDIS_URL=redis://redis:6379
      - DATABASE_URL=postgresql://rva:${POSTGRES_PASSWORD:-rva_secret}@postgres:5432/rva_metadata
      - GCS_BUCKET=${GCS_FRAMES_BUCKET:-frames}
      - GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcs-key.json
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3

  # Streamlit dashboard
  streamlit:
    build: ./streamlit
    container_name: rva-streamlit
    ports:
      - "8501:8501"
    depends_on:
      backend:
        condition: service_healthy
    environment:
      - BACKEND_URL=http://backend:8000
      - GCS_BUCKET=${GCS_FRAMES_BUCKET:-frames}

  # System monitoring
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
```

---

## Related Documents

- [01_ARCHITECTURE_ANALYSIS.md](./01_ARCHITECTURE_ANALYSIS.md) - System architecture overview
- [03_DATABASE_SCHEMA.md](./03_DATABASE_SCHEMA.md) - Database schema details
- [04_VISUALIZATION_REQUIREMENTS.md](./04_VISUALIZATION_REQUIREMENTS.md) - Visualization requirements
