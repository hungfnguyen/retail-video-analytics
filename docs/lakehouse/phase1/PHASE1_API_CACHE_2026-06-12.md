# Phase 1.1 - Analyst API Cache

Ngày thực hiện: 2026-06-12

Mục tiêu:

- Giảm latency analyst endpoints mà không đụng vào contract API.
- Chặn bớt truy vấn Trino lặp lại trên hot path.
- Tạo nền cho các bước tiếp theo: maintenance định kỳ, precompute `unique_tracks`, migrate v1 -> v2.

---

## 1. Phạm vi đã implement

Đã thêm Redis cache tại API layer cho 4 endpoint:

- `GET /api/v1/analytics/dashboard`
- `GET /api/v1/analytics/queue`
- `GET /api/v1/analytics/heatmap`
- `GET /api/v1/analytics/alerts`

File chính:

- `services/api/src/rva_api/api/v1/analytics.py`

Test mới:

- `tests/unit/test_analytics_api.py`

Không đổi:

- response schema
- query SQL hiện tại
- frontend contract
- Flink / Trino / Iceberg jobs

---

## 2. Thiết kế cache

### 2.1. Backend cache store

Cache dùng Redis hiện có của hệ thống, cùng config env với API live:

```text
REDIS_HOST
REDIS_PORT / REDIS_HOST_PORT
REDIS_PASSWORD
REDIS_DB
```

Nếu Redis không sẵn:

- analytics endpoint vẫn chạy bình thường;
- cache tự động fallback thành `no-cache`;
- không raise lỗi 503.

### 2.2. Key namespace

Pattern:

```text
analytics:cache:v1:<endpoint>:<params...>
```

Ví dụ:

```text
analytics:cache:v1:dashboard:days_7
analytics:cache:v1:queue:days_7
analytics:cache:v1:heatmap:cam_01:days_1:metric_presence
analytics:cache:v1:alerts:days_7
```

### 2.3. TTL policy

Mặc định:

```text
dashboard: 120s
queue:     120s
heatmap 1d: 300s
heatmap 7d+: 900s
alerts:    300s
empty result: 60s
error:     không cache
```

Env override:

```text
ANALYTICS_DASHBOARD_CACHE_TTL_SEC
ANALYTICS_QUEUE_CACHE_TTL_SEC
ANALYTICS_HEATMAP_CACHE_TTL_1D_SEC
ANALYTICS_HEATMAP_CACHE_TTL_LONG_SEC
ANALYTICS_ALERTS_CACHE_TTL_SEC
ANALYTICS_EMPTY_CACHE_TTL_SEC
```

Lý do:

- `dashboard` và `queue` đang bị người dùng poll mỗi `30s`, nên TTL `120s` giảm tải mạnh nhưng vẫn đủ tươi cho màn hình analyst.
- `heatmap` là historical view, không cần tươi từng giây.
- `empty` chỉ cache ngắn để tránh cố định trạng thái rỗng quá lâu trong giai đoạn warm-up.
- `error` không cache để tránh giữ lỗi giả sau khi hạ tầng hồi phục.

---

## 3. Hành vi cache

### 3.1. Cache hit

Nếu key đã tồn tại:

- API đọc JSON từ Redis;
- validate lại bằng Pydantic model tương ứng;
- trả về payload cached, bao gồm `generated_at` của lần build trước.

### 3.2. Cache miss

Nếu chưa có key:

- API chạy query Trino như cũ;
- chỉ cache payload `data_status in {"ready", "empty"}`;
- không cache payload `error`.

### 3.3. Correctness guard

Nếu cache payload hỏng hoặc parse lỗi:

- API bỏ cache entry đó;
- chạy cold path bình thường;
- không làm hỏng request.

---

## 4. Verification đã chạy

Đã chạy unit test:

```bash
uv run pytest tests/unit/test_analytics_queries.py tests/unit/test_analytics_api.py
```

Kết quả:

```text
9 passed
```

Đã chạy lint:

```bash
uv run ruff check services/api/src/rva_api/api/v1/analytics.py tests/unit/test_analytics_queries.py tests/unit/test_analytics_api.py
```

Kết quả:

```text
All checks passed
```

### 4.1. Những gì test đang cover

- `dashboard` response `ready` được cache và request thứ hai không chạy lại query builder.
- `dashboard` response `error` không bị cache.
- `queue` response `ready` được cache.
- `heatmap` response `empty` được cache với TTL ngắn hơn.

---

## 5. Runtime note quan trọng

Trong lúc implement, kiểm tra Redis key:

```bash
docker exec redis redis-cli --scan --pattern 'analytics:cache:v1:*'
```

chưa thấy key xuất hiện trên stack đang chạy.

Diễn giải hợp lý nhất:

- API host process đang chạy trước khi code mới được load;
- process hiện tại có thể chưa reload;
- vì vậy cache logic mới chưa đi vào request path runtime hiện tại.

Điều này **không phủ định** implementation:

- unit tests đã pass;
- code path cache đã có trong source;
- để verify end-to-end cần restart/reload API process rồi đo lại.

---

## 6. Cách verify end-to-end sau khi restart API

### 6.1. Khởi động lại API

Ví dụ nếu đang chạy host-side:

```bash
uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000
```

### 6.2. Gọi tuần tự cùng endpoint

Dashboard:

```bash
curl -sS -o /dev/null -w 'dashboard_1 %{http_code} %{time_total}\n' 'http://localhost:8000/api/v1/analytics/dashboard?days=7'
curl -sS -o /dev/null -w 'dashboard_2 %{http_code} %{time_total}\n' 'http://localhost:8000/api/v1/analytics/dashboard?days=7'
```

Queue:

```bash
curl -sS -o /dev/null -w 'queue_1 %{http_code} %{time_total}\n' 'http://localhost:8000/api/v1/analytics/queue?days=7'
curl -sS -o /dev/null -w 'queue_2 %{http_code} %{time_total}\n' 'http://localhost:8000/api/v1/analytics/queue?days=7'
```

Heatmap:

```bash
curl -sS -o /dev/null -w 'heatmap_1 %{http_code} %{time_total}\n' 'http://localhost:8000/api/v1/analytics/heatmap?camera_id=cam_01&days=1'
curl -sS -o /dev/null -w 'heatmap_2 %{http_code} %{time_total}\n' 'http://localhost:8000/api/v1/analytics/heatmap?camera_id=cam_01&days=1'
```

### 6.3. Kiểm tra key cache trong Redis

```bash
docker exec redis redis-cli --scan --pattern 'analytics:cache:v1:*'
```

Kỳ vọng:

- request đầu chậm hơn;
- request thứ hai nhanh hơn đáng kể;
- Redis có key `analytics:cache:v1:*`.

---

## 7. Đánh giá phase này

### 7.1. Giá trị đạt được

- Chặn ngay vấn đề analyst API quá chậm mà không đòi thay đổi Trino/Flink.
- Giảm lặp query nặng trên hot path.
- Giữ nguyên contract frontend/backend.
- Tách rõ 2 lớp việc:
  - `cache`: giải quyết latency người dùng;
  - `precompute/mart`: giải quyết chi phí compute nền.

### 7.2. Giới hạn hiện tại

- Cache không làm query gốc rẻ hơn; chỉ giảm tần suất đụng query gốc.
- Cold request đầu tiên vẫn chậm.
- Nếu API chạy nhiều process nhưng không cùng Redis, cache sẽ không chia sẻ được. Trong repo hiện tại, Redis là shared nên không có vấn đề này.
- `unique_tracks` vẫn đang exact distinct trên `silver_detections` v1 trong cold path.

---

## 8. Bước tiếp theo đề xuất

### Phase 1.2

Thiết lập maintenance định kỳ:

- `OPTIMIZE` cho `silver_detections`, `silver_detections_v2`, `gold_camera_*`, `gold_queue_sessions`
- audit file count / avg file size
- lên lịch bằng cron hoặc Airflow sau

### Phase 1.3

Precompute / rollup cho `unique_tracks`:

- tạo aggregate đúng grain dashboard;
- bỏ `COUNT(DISTINCT ...)` khỏi request path;
- đây là bước xử lý gốc cho cold latency.

### Phase 1.4

Debug `gold_zone_minute_metrics = 0`.

### Phase 1.5

Migrate dashboard lineage từ `silver_detections` v1 sang `silver_detections_v2`.

