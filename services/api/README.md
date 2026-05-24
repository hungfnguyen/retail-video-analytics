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
GET /media/live/{camera_id}/stream
POST /media/live/{camera_id}/webrtc/offer
```

Example:

```text
http://localhost:8000/api/v1/live/cam_01/dashboard
```

## Current Scope

- FastAPI application shell
- CORS for the local Vite frontend
- Live dashboard Redis serving contract
- MJPEG live video fallback
- WebRTC live video offer endpoint for the dashboard media plane
- Pydantic response models matching the frontend Live feature types
