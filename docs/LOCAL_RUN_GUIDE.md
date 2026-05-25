# Local Run Guide

This guide explains how to run the Retail Video Analytics project locally for development and demo.

## Prerequisites

- Docker Desktop
- Docker Compose
- Python 3.12+
- uv
- Node.js 20+
- npm

## 1. Start Infrastructure

Run from the repository root:

```bash
docker compose up -d --build
```

This starts the local infrastructure stack:

- Pulsar
- Flink
- MinIO
- Iceberg REST
- Trino

Check containers:

```bash
docker compose ps
```

## 2. Install Python Dependencies

Run from the repository root:

```bash
uv sync --all-packages
```

## 3. Run Vision Service

Run from the repository root:

```bash
uv run --package rva-vision python services/vision/main.py
```

The Vision service reads the configured video sources, runs YOLO + tracking, publishes metadata to Pulsar, and uploads sampled frames to MinIO when media upload is enabled.

## 4. Run FastAPI Backend

Open a second terminal at the repository root:

```bash
uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000
```

Current API checks:

```text
http://localhost:8000/health
http://localhost:8000/api/v1/live/cam_01/dashboard
```

The current API starts with mock Live dashboard data. Real Redis, Trino, MinIO, and Prometheus integrations can be added behind the same API contract later.

## 5. Run Frontend

Open a third terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL:

```text
http://localhost:5173
```

The frontend reads the API base URL from:

```text
frontend/.env.local
```

Default value:

```env
VITE_API_BASE_URL=http://localhost:8000
```

## Service URLs

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| FastAPI | http://localhost:8000 |
| FastAPI Docs | http://localhost:8000/docs |
| Flink UI | http://localhost:8081 |
| Trino | http://localhost:8083 |
| MinIO Console | http://localhost:9001 |
| Iceberg REST | http://localhost:8181 |

## Minimal Frontend Demo Mode

For UI-only work, Docker and Vision are not required.

Run only:

```bash
uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000
```

Then:

```bash
cd frontend
npm run dev
```

This mode uses the FastAPI mock dashboard endpoint.

## Full Pipeline Demo Mode

For a full data pipeline demo, run the commands in this order:

```bash
docker compose up -d --build
uv sync --all-packages
uv run --package rva-vision python services/vision/main.py
```

Then start the API and frontend in separate terminals:

```bash
uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000
```

```bash
cd frontend
npm run dev
```
