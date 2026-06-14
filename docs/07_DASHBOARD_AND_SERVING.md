# Dashboard And Serving

## Serving Architecture

```text
Redis live state ----\
                     FastAPI -> React frontend
Latest JPEG files ---/

Gold serving Iceberg tables -> Trino -> FastAPI analytics endpoint -> React analytics page
```

FastAPI is the backend-for-frontend. It exposes live dashboard JSON and media endpoints.

## Implemented API

| Endpoint | Purpose |
|---|---|
| `GET /health` | API health |
| `GET /api/v1/live/{camera_id}/dashboard` | Live dashboard data from Redis and live media metadata |
| `GET /api/v1/analytics/dashboard` | Historical analytics from Trino over compact Gold aggregate tables |
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
- heatmap points, zone heatmap, zone occupancy, and queue-zone wait summaries;
- recent alerts from Redis keys `alerts:recent:{camera_id}` and `alerts:recent:store:{store_id}`;
- empty traffic arrays until traffic direction events are backed by real endpoints;
- simple pipeline health for Redis/FastAPI.

Realtime density alerts are written by `RealtimeMetricsJob` when the per-frame
people count exceeds `ALERT_DENSITY_THRESHOLD`. Redis keeps only recent alert
state with TTL and cooldown; historical alert events are written to
`rva.gold_alert_events` records frame-level density signals. Clip-backed alert
incidents are written to `rva.gold_alerts` and used by alert history / alert
serving. Video clips stay outside Redis and are linked through `clip_s3_key` /
`clip_s3_uri` metadata when clip extraction is enabled.

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
| Analytics | Connected to FastAPI analytics endpoint backed by Trino and Gold serving tables |
| System | UI exists; service cards partially use live API; deeper system metrics are pending |

## Next Serving Work

- Add narrower analytics endpoints for drill-down and exports.
- Continue moving expensive historical panels to Gold serving tables.
- Add system health endpoints for Pulsar, Flink, Trino, S3, Redis, and API.
- Replace placeholder traffic with real entry/exit data contracts.
- Add cache and query limits for analytical endpoints.
