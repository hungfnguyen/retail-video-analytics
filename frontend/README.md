# RVA Frontend

React + TypeScript + Vite dashboard for Retail Video Analytics.

## Pages

| Page | Status |
|---|---|
| Live | Connected to FastAPI live endpoint and media stream |
| Analytics | Connected to FastAPI analytics and queue endpoints backed by Trino over Silver/Gold tables |
| Heatmap | Connected to FastAPI presence heatmap endpoint backed by `silver_detections_v2` |
| System | Connected to FastAPI system dashboard endpoint |

## Run

```bash
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

## Environment

Create `frontend/.env.local` when needed:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_LIVE_VIDEO_TRANSPORT=webrtc
```

Set `VITE_LIVE_VIDEO_TRANSPORT=mjpeg` to force MJPEG fallback.

## Build

```bash
npm run build
```
