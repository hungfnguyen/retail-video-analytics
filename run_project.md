# Run Project

Chạy từ thư mục root:

```bash
cd /home/hungfnguyen/project/retail-video-analytics
```

## 1. Cài dependencies

```bash
uv sync --all-packages

cd frontend
npm install
cd ..
```

## 2. Start infrastructure

```bash
docker compose up -d --build
docker compose ps
```

Đợi các service chính chạy ổn:

- `pulsar-broker`
- `redis`
- `flink-jobmanager`
- `flink-taskmanager`
- `iceberg-rest`
- `trino`

## 3. Start Vision service

Mở terminal mới:

```bash
cd /home/hungfnguyen/project/retail-video-analytics
uv run --package rva-vision python services/vision/main.py
```

Vision sẽ:

- đọc camera/video từ `configs/cameras.yaml`;
- chạy YOLO + tracking;
- publish metadata vào Pulsar;
- ghi annotated live frame vào `runtime/live_frames/{camera_id}.jpg`.

## 4. Start FastAPI

Mở terminal mới:

```bash
cd /home/hungfnguyen/project/retail-video-analytics
uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000
```

Kiểm tra:

```text
http://localhost:8000/health
http://localhost:8000/api/v1/live/cam_01/dashboard
http://localhost:8000/media/live/cam_01/stream
```

API media hiện có:

- WebRTC: `POST /media/live/{camera_id}/webrtc/offer`
- MJPEG fallback: `GET /media/live/{camera_id}/stream`
- Snapshot: `GET /media/live/{camera_id}/snapshot.jpg`

## 5. Start Frontend

Mở terminal mới:

```bash
cd /home/hungfnguyen/project/retail-video-analytics/frontend
npm run dev
```

Mở dashboard:

```text
http://localhost:5173
```

Frontend mặc định gọi API:

```text
http://localhost:8000
```

Nếu cần ép UI dùng MJPEG thay vì WebRTC, tạo `frontend/.env.local`:

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_LIVE_VIDEO_TRANSPORT=mjpeg
```

Sau đó restart `npm run dev`.

## 6. Verify realtime data

Redis:

```bash
docker exec redis redis-cli GET stats:count:cam_01
docker exec redis redis-cli ZREVRANGE heatmap:live:cam_01 0 10 WITHSCORES
docker exec redis redis-cli KEYS "track:active:cam_01:*"
```

Flink:

```text
http://localhost:8081
```

Frontend:

```text
http://localhost:5173
```

## 7. Stop project

Dừng Vision, FastAPI, Frontend bằng `Ctrl+C` ở từng terminal.

Dừng infrastructure:

```bash
docker compose down
```

Reset toàn bộ local state nếu cần:

```bash
docker compose down -v
```
