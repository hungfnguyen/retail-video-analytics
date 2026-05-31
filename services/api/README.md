# RVA API

FastAPI backend for the React dashboard.

## Implemented Responsibilities

- Live dashboard endpoint backed by Redis and live media metadata.
- MJPEG stream and snapshot endpoint from latest annotated JPEG files.
- WebRTC offer/answer endpoint backed by latest JPEG frames.
- Basic `/health` endpoint.

## Endpoints

```text
GET  /health
GET  /api/v1/live/{camera_id}/dashboard
GET  /media/live/{camera_id}/snapshot.jpg
GET  /media/live/{camera_id}/stream
POST /media/live/{camera_id}/webrtc/offer
```

## Run

```bash
uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000
```

## Environment

| Variable | Purpose |
|---|---|
| `REDIS_HOST` | Redis host, defaults to local/container config path |
| `REDIS_PORT` | Redis port |
| `RVA_LIVE_MEDIA_DIR` or `LIVE_MEDIA_DIR` | Directory containing latest live frames |
| `RVA_WEBRTC_VIDEO_FPS` or `LIVE_WEBRTC_VIDEO_FPS` | WebRTC pacing FPS |

The API currently focuses on realtime serving. Analytics endpoints over Trino are a future integration step.
