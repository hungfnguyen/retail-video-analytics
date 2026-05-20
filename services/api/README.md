# Dashboard API Service

This service is the backend gateway for the dashboard. It starts with mock data so the frontend can be built before Redis, Trino, and S3 integrations are ready.

## Run Locally

From the repository root:

```bash
uv sync --all-packages
uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000
```

## Endpoints

```text
GET /health
GET /api/v1/live/{camera_id}/dashboard
```

Example:

```text
http://localhost:8000/api/v1/live/cam_01/dashboard
```

## Current Scope

- FastAPI application shell
- CORS for the local Vite frontend
- Live dashboard mock contract
- Pydantic response models matching the frontend Live feature types

Real Redis, Trino, S3, and Prometheus integrations should be added behind the same API contract later.
