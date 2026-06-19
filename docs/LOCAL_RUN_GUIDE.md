# Local Run Guide

## 1. Install Dependencies

```bash
cd /home/hungfnguyen/project/retail-video-analytics
uv sync --all-packages
cd frontend
npm install
cd ..
```

## 2. Configure AWS S3

Create `.env` from `.env.example` and fill credentials.

```bash
cp .env.example .env
```

Verify AWS access:

```bash
aws sts get-caller-identity
aws s3 ls s3://retail-video-analytics-prod/
```

## 3. Start Infrastructure

```bash
cd D:\workspace\retail-video-analytics
docker compose up -d --build
docker compose ps
```

Expected services:

- `postgres`
- `airflow`
- `pulsar-broker`
- `pulsar-init`
- `flink-jobmanager`
- `flink-taskmanager`
- `flink-job-submitter`
- `redis`
- `iceberg-rest`
- `trino`

## 4. Start Vision

```bash
uv run --package rva-vision python services/vision/main.py
```

## 5. Start FastAPI

```bash
uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000
```

Verify:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/live/cam_01/dashboard
```

## 6. Start Frontend

```bash
cd frontend
npm run dev
```

Open:

```text
http://localhost:5173
```

## 7. Verify Pipeline

```bash
curl -s http://localhost:8081/jobs/overview

docker exec redis redis-cli GET stats:count:cam_01

docker exec trino trino --execute "SHOW TABLES FROM lakehouse.rva"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.bronze_raw"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.silver_detections_v2"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.gold_track_summary_v2"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.gold_queue_sessions"
docker exec trino trino --execute "SHOW TABLES FROM lakehouse.rva_gold_serving"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva_gold_serving.gold_serving_traffic_daily"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva_gold_serving.gold_serving_executive_daily"

curl http://localhost:8000/api/v1/analytics/dashboard?days=7
```

## 8. Stop

Stop Vision, API, and Frontend with `Ctrl+C` in their terminals.

Stop infrastructure:

```bash
docker compose down
```

Reset infrastructure state:

```bash
docker compose down -v
```
