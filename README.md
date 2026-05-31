# Retail Video Analytics

Data Engineering project for retail video analytics. The current implementation is an as-built realtime + lakehouse system:

```text
YOLO11 + BoTSORT
  -> Pulsar
  -> Flink dual path
      -> Redis realtime state
      -> Iceberg tables on AWS S3
  -> Trino
  -> FastAPI
  -> React frontend
```

## Current Scope

The project focuses on metadata extracted from video, not storing raw video as analytical data. Vision produces detection events; Flink turns those events into realtime state and lakehouse tables.

Implemented now:

- Multi-camera Vision worker from `configs/cameras.yaml`.
- Detection and tracking with YOLO11 + BoTSORT/ByteTrack.
- Pulsar metadata ingestion.
- Flink lakehouse path: `bronze_raw`, `silver_detections`, `gold_track_summary`.
- Flink realtime path: Redis count, active tracks, heatmap, latest frame snapshot, DLQ.
- AWS S3 storage for Iceberg tables and optional sampled frames/clips.
- Trino SQL query over Iceberg.
- FastAPI live dashboard and media serving endpoints.
- React frontend with Live, Analytics, and System pages. Live is connected to realtime data; Analytics/System still need deeper API integration.

## Runtime Services

| Service | Port | Purpose |
|---|---:|---|
| Pulsar broker | 6650 | Binary protocol for producers/consumers |
| Pulsar admin | 8084 | Broker health and topic admin API |
| Flink UI | 8081 | Job status and exceptions |
| Iceberg REST | 8181 | Iceberg catalog service |
| Trino | 8083 | SQL query engine |
| Redis | 6379 | Realtime state |
| FastAPI | 8000 | Dashboard API and media gateway |
| Frontend | 5173 | React dashboard |

AWS S3 is accessed through the AWS endpoint configured in `.env`; there is no local object-storage service in the current architecture.

## Main Data Flow

```text
Vision service
  |-- annotated latest JPEG -> runtime/live_frames/{camera_id}.jpg
  |-- optional sampled media -> s3://retail-video-analytics-prod/frames|clips
  `-- detection JSON -> Pulsar persistent://retail/metadata/events

Pulsar events
  |-- BronzeIngestJob -> lakehouse.rva.bronze_raw
  |-- RealtimeMetricsJob -> Redis + DLQ

bronze_raw -> SilverJob -> lakehouse.rva.silver_detections
silver_detections -> GoldTrackSummaryJob -> lakehouse.rva.gold_track_summary

Trino queries Iceberg tables.
FastAPI reads Redis/live frames/Trino-facing data and serves the React frontend.
```

## Repository Layout

```text
configs/                 Camera and logging configuration
docs/                    Current architecture and run documentation
frontend/                React dashboard
infrastructure/          Pulsar, Flink, Trino container config
packages/                Shared Python packages: core, messaging, storage
services/api/            FastAPI backend
services/flink-jobs/     Java Flink jobs
services/vision/         Vision processing service
tests/                   Unit and integration tests
```

## Environment

Create `.env` from `.env.example` and fill AWS credentials:

```bash
cp .env.example .env
```

Required storage variables:

```env
S3_ENDPOINT=https://s3.ap-southeast-2.amazonaws.com
S3_PATH_STYLE=false
S3_REGION=ap-southeast-2
S3_ACCESS_KEY=CHANGE_ME
S3_SECRET_KEY=CHANGE_ME
ICEBERG_CATALOG_URI=http://iceberg-rest:8181
ICEBERG_WAREHOUSE=s3a://retail-video-analytics-prod/lakehouse
```

For Vision media upload, `configs/cameras.yaml` currently uses bucket `retail-video-analytics-prod`.

## Start Project

From repository root:

```bash
uv sync --all-packages
cd frontend && npm install && cd ..
```

Start infrastructure:

```bash
docker compose up -d --build
```

Start Vision:

```bash
uv run --package rva-vision python services/vision/main.py
```

Start API:

```bash
uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000
```

Start frontend:

```bash
cd frontend
npm run dev
```

Open:

```text
http://localhost:5173
```

## Verify

Flink jobs:

```bash
curl -s http://localhost:8081/jobs/overview
```

Pulsar health:

```bash
curl -s http://localhost:8084/admin/v2/brokers/health
```

Redis realtime state:

```bash
docker exec redis redis-cli GET stats:count:cam_01
docker exec redis redis-cli ZREVRANGE heatmap:live:cam_01 0 10 WITHSCORES
docker exec redis redis-cli KEYS 'track:active:cam_01:*'
```

Iceberg tables through Trino:

```bash
docker exec trino trino --execute "SHOW TABLES FROM lakehouse.rva"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.bronze_raw"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.silver_detections"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.gold_track_summary"
```

AWS S3 layout:

```bash
aws s3 ls s3://retail-video-analytics-prod/
aws s3 ls s3://retail-video-analytics-prod/lakehouse/ --recursive | head
aws s3 ls s3://retail-video-analytics-prod/frames/ --recursive | head
```

## Tests

```bash
uv run pytest tests/unit/test_live_api.py tests/unit/test_live_video_media.py tests/unit/test_live_frame_publisher.py tests/integration/test_s3_client_config.py
cd frontend && npm run build
```

## Documentation

Start with [docs/README.md](docs/README.md). The docs are now maintained as current implementation docs, not future design notes.
