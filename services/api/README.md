# RVA API

FastAPI backend for the React dashboard.

## Implemented Responsibilities

- Live dashboard endpoint backed by Redis and live media metadata.
- Analytics dashboard endpoint backed by Trino over Iceberg Silver/Gold tables.
- MJPEG stream and snapshot endpoint from latest annotated JPEG files.
- WebRTC offer/answer endpoint backed by latest JPEG frames.
- Basic `/health` endpoint.

## Endpoints

```text
GET  /health
GET  /api/v1/live/{camera_id}/dashboard
GET  /api/v1/analytics/dashboard
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
| `REDIS_HOST` | Redis host, defaults to `localhost` for host-side API runs |
| `REDIS_PORT` | Redis port, defaults to `REDIS_HOST_PORT` or `16379`; Docker services still use `redis:6379` |
| `RVA_LIVE_MEDIA_DIR` or `LIVE_MEDIA_DIR` | Directory containing latest live frames |
| `RVA_WEBRTC_VIDEO_FPS` or `LIVE_WEBRTC_VIDEO_FPS` | WebRTC pacing FPS |
| `TRINO_URL` | Trino HTTP endpoint, defaults to `http://localhost:8083` |
| `TRINO_QUERY_TIMEOUT_SEC` | Per-request Trino HTTP timeout in seconds, defaults to `5` |
| `TRINO_QUERY_MAX_WAIT_SEC` | Maximum wait for one Trino query to finish, defaults to `60` |

The analytics endpoint returns honest empty/error states when Trino is unavailable or the lakehouse has no rows.
