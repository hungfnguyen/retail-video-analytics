# Dashboard And Serving

## Serving Architecture

```text
Redis live state ----\
                     FastAPI -> React frontend
Latest JPEG files ---/

Iceberg tables -> Trino -> future analytics API endpoints -> React analytics page
```

FastAPI is the backend-for-frontend. It exposes live dashboard JSON and media endpoints.

## Implemented API

| Endpoint | Purpose |
|---|---|
| `GET /health` | API health |
| `GET /api/v1/live/{camera_id}/dashboard` | Live dashboard data from Redis and live media metadata |
| `GET /api/v1/analytics/dashboard` | Historical analytics from Trino over Iceberg Silver/Gold tables |
| `GET /media/live/{camera_id}/snapshot.jpg` | Latest JPEG snapshot |
| `GET /media/live/{camera_id}/stream` | MJPEG fallback stream |
| `POST /media/live/{camera_id}/webrtc/offer` | WebRTC offer/answer endpoint |

## Live Dashboard Contract

`/api/v1/live/{camera_id}/dashboard` returns:

- store and camera metadata;
- current frame metadata;
- current count and active track count;
- media FPS and media latency;
- metadata freshness;
- heatmap points and zone heatmap;
- empty arrays for alerts/traffic until those features are backed by real endpoints;
- simple pipeline health for Redis/FastAPI.

## Media Serving

The current media path is:

```text
Vision annotated JPEG -> runtime/live_frames -> FastAPI -> browser
```

Frontend defaults to WebRTC and falls back to MJPEG if WebRTC fails or is disabled with:

```env
VITE_LIVE_VIDEO_TRANSPORT=mjpeg
```

## Frontend Status

| Page | Status |
|---|---|
| Live | Connected to FastAPI realtime endpoint and media stream |
| Analytics | Connected to FastAPI analytics endpoint backed by Trino |
| System | UI exists; service cards partially use live API; deeper system metrics are pending |

## Next Serving Work

- Add narrower analytics endpoints for drill-down and exports.
- Add system health endpoints for Pulsar, Flink, Trino, S3, Redis, and API.
- Replace placeholder traffic/alerts with real data contracts.
- Add cache and query limits for analytical endpoints.
