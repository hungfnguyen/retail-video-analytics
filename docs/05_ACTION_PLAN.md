# Implementation Guide

## Overview

This document describes the implementation roadmap organized into phases with clear priorities and dependencies.

---

## 1. Priority Matrix

| Priority | Component | Effort | Impact | Dependencies |
|----------|-----------|--------|--------|--------------|
| **P1** | Fast Path (Redis + WebSocket) | 2-3 days | High | None |
| **P2** | Media Storage (GCS) | 1-2 days | High | None |
| **P3** | Metadata Database (PostgreSQL) | 1 day | High | None |
| **P4** | Streamlit Dashboard | 3-5 days | High | P1, P2, P3 |
| **P5** | Grafana + Prometheus | 1 day | Medium | None |

**Total Timeline:**
- Phase 1 (P1-P3): 4-6 days
- Phase 2 (P4): 3-5 days
- Phase 3 (P5): 1 day
- **Total: 8-12 days**

---

## 2. Phase 1: Backend Infrastructure

### 2.1 Setup Redis

**Duration:** 0.5 days

**docker-compose.yml addition:**
```yaml
redis:
  image: redis:7-alpine
  container_name: rva-redis
  ports:
    - "6379:6379"
  volumes:
    - redis_data:/data
  command: redis-server --appendonly yes
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 10s
    timeout: 5s
    retries: 5
```

**Verification:**
```bash
docker-compose up -d redis
redis-cli ping  # Should return PONG
```

### 2.2 Setup PostgreSQL

**Duration:** 0.5 days

**docker-compose.yml addition:**
```yaml
postgres:
  image: postgres:16-alpine
  container_name: rva-postgres
  environment:
    POSTGRES_DB: rva_metadata
    POSTGRES_USER: rva
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-rva_secret}
  ports:
    - "5432:5432"
  volumes:
    - postgres_data:/var/lib/postgresql/data
    - ./scripts/sql/init.sql:/docker-entrypoint-initdb.d/init.sql
  healthcheck:
    test: ["CMD-SHELL", "pg_isready -U rva -d rva_metadata"]
    interval: 10s
    timeout: 5s
    retries: 5
```

**Migration script (scripts/sql/init.sql):**
```sql
-- See 03_DATABASE_SCHEMA.md for full schema
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS system;

-- Create tables...
```

### 2.3 Configure GCS for Media Storage

**Duration:** 0.5 days

**Create bucket:**
```bash
# Create bucket with lifecycle policy (7-day retention for frames)
gsutil mb -p my-gcp-project -l us-central1 gs://rva-frames

# Set lifecycle policy
cat > lifecycle.json << 'EOF'
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 7}}]}
EOF
gsutil lifecycle set lifecycle.json gs://rva-frames
```

**Vision module: vision/emit/frame_saver.py:**
```python
from google.cloud import storage
from datetime import datetime
import cv2

class FrameSaver:
    def __init__(self, bucket_name: str = "rva-frames", save_interval: int = 1):
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)
        self.save_interval = save_interval
        self._last_save: float = 0.0

    def save_frame(self, frame, camera_id, timestamp):
        import time
        now = time.monotonic()
        if (now - self._last_save) < self.save_interval:
            return None
        self._last_save = now

        # Generate GCS blob path
        dt = datetime.fromisoformat(timestamp)
        blob_name = f"{dt.strftime('%Y-%m-%d')}/{camera_id}/{dt.strftime('%H')}/{dt.strftime('%H-%M-%S')}.jpg"

        # Encode frame
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        # Upload
        blob = self.bucket.blob(blob_name)
        blob.upload_from_string(buffer.tobytes(), content_type='image/jpeg')

        return f"gs://{self.bucket.name}/{blob_name}"
```

### 2.4 Implement Fast Path Flink Job

**Duration:** 1-2 days

**AlertingJob.java:**
```java
package org.rva.alerting;

import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.cep.CEP;
import org.apache.flink.cep.PatternStream;
import org.apache.flink.cep.pattern.Pattern;
import org.apache.flink.cep.pattern.conditions.SimpleCondition;
import org.apache.flink.streaming.api.windowing.time.Time;

public class AlertingJob {

    public static void main(String[] args) throws Exception {
        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();

        // Source: Pulsar
        DataStream<Detection> detections = createPulsarSource(env);

        // Pattern 1: Crowd detection — >= 20 people within 5 seconds (density-based, no zones)
        Pattern<Detection, ?> crowdPattern = Pattern
            .<Detection>begin("crowd_start")
            .where(new SimpleCondition<Detection>() {
                @Override
                public boolean filter(Detection event) {
                    return event.getObjectClass().equals("person")
                        && event.getConfidence() >= 0.4;
                }
            })
            .timesOrMore(20)
            .within(Time.seconds(5));

        // Pattern 2: Density spike — >= 30 people within 30 seconds
        Pattern<Detection, ?> densitySpikePattern = Pattern
            .<Detection>begin("spike")
            .where(new SimpleCondition<Detection>() {
                @Override
                public boolean filter(Detection event) {
                    return event.getObjectClass().equals("person");
                }
            })
            .timesOrMore(30)
            .within(Time.seconds(30));

        // Key by camera_id (not zone_id — zones removed)
        PatternStream<Detection> crowdStream = CEP.pattern(
            detections.keyBy(Detection::getCameraId),
            crowdPattern
        );

        PatternStream<Detection> spikeStream = CEP.pattern(
            detections.keyBy(Detection::getCameraId),
            densitySpikePattern
        );

        // Process matches into Alert objects
        DataStream<Alert> crowdAlerts = crowdStream.process(new CrowdAlertProcessor());
        DataStream<Alert> spikeAlerts = spikeStream.process(new DensitySpikeProcessor());
        DataStream<Alert> allAlerts = crowdAlerts.union(spikeAlerts);

        // Sinks
        allAlerts.addSink(new RedisSink());
        allAlerts.addSink(new PostgresSink());

        env.execute("RVA Alerting Job");
    }
}
```

**RedisSink:**
```java
public class RedisSink extends RichSinkFunction<Alert> {
    private Jedis jedis;

    @Override
    public void open(Configuration parameters) {
        jedis = new Jedis("redis", 6379);
    }

    @Override
    public void invoke(Alert alert, Context context) {
        // Add to alert queue (keep last 100)
        jedis.lpush("alert:queue", alert.toJson());
        jedis.ltrim("alert:queue", 0, 99);

        // Publish to WebSocket channel
        jedis.publish("channel:alerts", alert.toJson());
    }
}
```

### 2.5 Implement WebSocket Server

**Duration:** 0.5 days

**backend/websocket_server.py:**
```python
import asyncio
import json
import redis.asyncio as redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Set

app = FastAPI()
redis_client = None
connected_clients: Set[WebSocket] = set()

@app.on_event("startup")
async def startup():
    global redis_client
    redis_client = redis.from_url("redis://redis:6379")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)

    try:
        # Subscribe to Redis channels
        pubsub = redis_client.pubsub()
        await pubsub.subscribe("channel:detections", "channel:alerts", "channel:heatmap")

        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                await websocket.send_json(data)
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
    finally:
        await pubsub.unsubscribe()

@app.get("/api/realtime/stats/{camera_id}")
async def get_stats(camera_id: str):
    count = await redis_client.get(f"stats:count:{camera_id}")
    return {"camera_id": camera_id, "current_count": int(count or 0)}

@app.get("/api/realtime/heatmap/{camera_id}")
async def get_heatmap(camera_id: str):
    data = await redis_client.zrevrange(
        f"heatmap:live:{camera_id}", 0, -1, withscores=True
    )
    hotspots = [{"cell": k.decode(), "density": v} for k, v in data]
    return {"camera_id": camera_id, "hotspots": hotspots}

@app.get("/api/realtime/alerts")
async def get_alerts():
    alerts = await redis_client.lrange("alert:queue", 0, 9)
    return [json.loads(a) for a in alerts]
```

---

## 3. Phase 2: Streamlit Dashboard

### 3.1 Project Structure

**Duration:** 0.5 days

```
streamlit/
├── app.py                 # Main app entry
├── pages/
│   ├── 1_Live_Monitor.py
│   ├── 2_Heatmap.py
│   ├── 3_Event_Search.py
│   ├── 4_Track_Replay.py
│   └── 5_Analytics.py
├── components/
│   ├── video_player.py
│   ├── heatmap_overlay.py
│   └── alert_panel.py
├── services/
│   ├── redis_client.py
│   ├── postgres_client.py
│   ├── gcs_client.py
│   └── websocket_client.py
├── utils/
│   ├── config.py
│   └── helpers.py
├── requirements.txt
└── Dockerfile
```

### 3.2 Core Services

**Duration:** 1 day

**services/redis_client.py:**
```python
import redis
from typing import Dict, List, Tuple
import json

class RedisService:
    def __init__(self, host='redis', port=6379):
        self.client = redis.Redis(host=host, port=port, decode_responses=True)

    def get_heatmap(self, camera_id: str) -> List[Tuple[str, float]]:
        return self.client.zrevrange(f"heatmap:live:{camera_id}", 0, -1, withscores=True)

    def get_active_alerts(self, limit: int = 10) -> List[dict]:
        alerts = self.client.lrange("alert:queue", 0, limit - 1)
        return [json.loads(a) for a in alerts]

    def get_active_tracks(self) -> List[str]:
        return self.client.keys("track:active:*")
```

**services/postgres_client.py:**
```python
import asyncpg
from typing import List, Optional
from datetime import datetime

class PostgresService:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(self.dsn)

    async def search_events(
        self,
        camera_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[dict]:
        query = "SELECT * FROM core.track_events WHERE 1=1"
        params = []
        param_idx = 1

        if camera_id:
            query += f" AND camera_id = ${param_idx}"
            params.append(camera_id)
            param_idx += 1

        if event_type:
            query += f" AND event_type = ${param_idx}"
            params.append(event_type)
            param_idx += 1

        if start_time:
            query += f" AND timestamp >= ${param_idx}"
            params.append(start_time)
            param_idx += 1

        if end_time:
            query += f" AND timestamp <= ${param_idx}"
            params.append(end_time)
            param_idx += 1

        query += f" ORDER BY timestamp DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
        params.extend([limit, offset])

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]

    async def get_track_journey(self, track_id: int) -> dict:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT * FROM core.tracks WHERE track_id = $1",
                track_id
            )
```

**services/gcs_client.py:**
```python
from google.cloud import storage
import datetime

class GCSService:
    def __init__(self, bucket_name: str):
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)

    def get_frame(self, frame_path: str) -> bytes:
        # frame_path: gs://rva-frames/2024-03-28/cam_01/14-30-00.jpg
        blob_name = frame_path.replace(f"gs://{self.bucket.name}/", "")
        blob = self.bucket.blob(blob_name)
        return blob.download_as_bytes()

    def get_frame_url(self, frame_path: str, expires_in: int = 3600) -> str:
        blob_name = frame_path.replace(f"gs://{self.bucket.name}/", "")
        blob = self.bucket.blob(blob_name)
        return blob.generate_signed_url(
            expiration=datetime.timedelta(seconds=expires_in),
            method="GET"
        )
```

### 3.3 Dashboard Pages

**Duration:** 2-3 days

**pages/1_Live_Monitor.py:**
```python
import streamlit as st
from services.redis_client import RedisService
from services.gcs_client import GCSService
from components.alert_panel import AlertPanel

st.set_page_config(page_title="Live Monitor", page_icon="📹", layout="wide")

redis = RedisService()
gcs = GCSService(bucket_name=st.secrets["GCS_FRAMES_BUCKET"])

st.title("Live Monitor")

cameras = ["cam_01", "cam_02", "cam_03"]
selected_camera = st.selectbox("Select Camera", cameras)

col1, col2 = st.columns([3, 1])

with col1:
    st.subheader(f"Camera: {selected_camera}")
    video_placeholder = st.empty()
    show_boxes = st.checkbox("Show Bounding Boxes", value=True)

with col2:
    st.subheader("Active Alerts")
    alerts = redis.get_active_alerts(5)
    for alert in alerts:
        with st.container():
            st.warning(f"Warning: {alert['type']} — Camera: {alert['camera_id']}")
            st.caption(alert['timestamp'])

st.button("Refresh")
```

### 3.4 Dockerfile for Streamlit

**Duration:** 0.5 days

**streamlit/Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

**streamlit/requirements.txt:**
```
streamlit>=1.30.0
redis>=5.0.0
asyncpg>=0.29.0
google-cloud-storage>=2.14.0
plotly>=5.18.0
opencv-python-headless>=4.9.0
pillow>=10.2.0
websockets>=12.0
numpy>=1.26.0
pandas>=2.1.0
```

---

## 4. Phase 3: Monitoring & Grafana

### 4.1 Setup Prometheus

**Duration:** 0.5 days

**docker-compose.yml addition:**
```yaml
prometheus:
  image: prom/prometheus:latest
  container_name: rva-prometheus
  ports:
    - "9090:9090"
  volumes:
    - ./configs/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    - prometheus_data:/prometheus
  command:
    - '--config.file=/etc/prometheus/prometheus.yml'
    - '--storage.tsdb.path=/prometheus'
```

**configs/prometheus/prometheus.yml:**
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'flink'
    static_configs:
      - targets: ['flink-jobmanager:8081']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']

  - job_name: 'pulsar'
    static_configs:
      - targets: ['pulsar:8080']
    metrics_path: /metrics
```

### 4.2 Update Grafana Dashboards

**Duration:** 0.5 days

**Add Prometheus datasource:**
```yaml
# configs/grafana/provisioning/datasources/prometheus.yml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: false
```

**Import System Health Dashboard with:**
- Flink metrics
- Redis metrics
- Pulsar metrics
- GCS metrics (via Cloud Monitoring)

---

## 5. Testing Checklist

### Unit Tests

- [ ] Redis service methods
- [ ] PostgreSQL queries
- [ ] GCS operations
- [ ] Flink CEP patterns

### Integration Tests

- [ ] End-to-end: Detection → Pulsar → Flink → Redis → WebSocket
- [ ] End-to-end: Detection → PostgreSQL → Streamlit Query
- [ ] End-to-end: Frame → GCS → Streamlit Display

### Performance Tests

- [ ] Redis: 10,000 ops/sec
- [ ] PostgreSQL: 1,000 queries/sec
- [ ] WebSocket: 100 concurrent connections
- [ ] Flink: < 500ms alerting latency

---

## 6. Deployment Checklist

### Pre-deployment

- [ ] All tests passing
- [ ] Docker images built
- [ ] Environment variables configured
- [ ] Database migrations ready

### Deployment Steps

```bash
# 1. Pull latest code
git pull origin main

# 2. Build images
docker-compose build

# 3. Start infrastructure
docker-compose up -d redis postgres

# 4. Run migrations
docker-compose exec postgres psql -U rva -d rva_metadata -f /migrations/all.sql

# 5. Start all services
docker-compose up -d

# 6. Verify health
docker-compose ps
curl http://localhost:8501/healthz  # Streamlit
curl http://localhost:8081/overview  # Flink
curl http://localhost:3000/api/health  # Grafana
```

### Post-deployment

- [ ] Verify all dashboards loading
- [ ] Test alert flow end-to-end
- [ ] Check Grafana metrics
- [ ] Monitor logs for errors

---

## Related Documents

- [02_ARCHITECTURE_IMPROVED.md](./02_ARCHITECTURE_IMPROVED.md) - Architecture details
- [03_DATABASE_SCHEMA.md](./03_DATABASE_SCHEMA.md) - Database setup
- [04_VISUALIZATION_REQUIREMENTS.md](./04_VISUALIZATION_REQUIREMENTS.md) - UI requirements
