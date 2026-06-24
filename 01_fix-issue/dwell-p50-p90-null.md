# Issue: Dwell Time P50/P90 không hiện trên Analytics Dashboard

**Ngày phát hiện:** 2026-06-24  
**Mức độ:** Medium — Avg Dwell Time đúng, nhưng P90 Dwell và Dwell Trend lines bị ẩn  
**Status:** Root cause xác định, chưa fix

---

## 1. Triệu chứng

Trên tab **Dwell Time** của Analytics Dashboard:

| MetricCard | Hiển thị | Mong đợi |
|---|---|---|
| Avg Dwell Time | `18s` ✅ | `18s` |
| P90 Dwell | `—` ❌ | `~Xm Ys` |
| Long Dwell Share | đúng ✅ | — |
| Observed Visits | đúng ✅ | — |

Dwell Trend chart: chỉ có **avg line** (xanh lá), P50 và P90 line vẽ **flat tại y=0** → không thấy được.

---

## 2. Quy trình tìm root cause

### Bước 1 — Kiểm tra API response

```bash
curl http://localhost:80/api/v1/analytics/dashboard?store_id=store_001&days=7
```

Kết quả:
```json
{
  "avg_dwell_sec": 18.2,
  "dwell_trend": [
    {
      "date": "2026-06-21",
      "avg_dwell_sec": 18.2,
      "p50_dwell_sec": 0.0,
      "p90_dwell_sec": 0.0
    }
  ]
}
```

→ `avg_dwell_sec = 18.2` đúng. `p50 = 0.0`, `p90 = 0.0` — **sai**, đây là dấu hiệu NULL bị convert thành 0.

### Bước 2 — Kiểm tra data trong serving table

```sql
SELECT camera_id, metric_date, track_count, avg_dwell_sec, p50_dwell_sec, p90_dwell_sec
FROM lakehouse.rva_gold_serving.gold_serving_dwell_daily
```

Kết quả:
```
cam_02 | 2026-06-21 | 5441 | 16.24 | (empty) | (empty)
cam_01 | 2026-06-21 |  375 | 47.48 | (empty) | (empty)
```

→ `p50_dwell_sec` và `p90_dwell_sec` là **NULL** trong Iceberg table.

### Bước 3 — Kiểm tra Airflow DAG

```bash
docker exec airflow airflow dags list-runs -d gold_serving_dwell
```

Kết quả: tất cả runs đều `success` — DAG chạy đúng, không phải lỗi pipeline.

### Bước 4 — Trace ngược về Flink batch SQL

Airflow DAG `gold_serving_dwell` → `submit_batch_job.py --domain dwell_daily` → Flink `GoldServingBatchJob` → `dwell_daily.sql`:

```sql
-- services/flink-jobs/java/src/main/resources/dwell_daily.sql
INSERT INTO rva_gold_serving.gold_serving_dwell_daily
SELECT
  ...
  AVG(CAST(duration_sec AS DOUBLE)) AS avg_dwell_sec,
  CAST(NULL AS DOUBLE) AS p50_dwell_sec,   -- ← HARDCODED NULL
  CAST(NULL AS DOUBLE) AS p90_dwell_sec,   -- ← HARDCODED NULL
  ...
FROM rva.gold_track_summary_v2
```

**Root cause xác định:** Flink SQL không có hàm `approx_percentile` (đây là Trino-only function). Dev đã hardcode `CAST(NULL AS DOUBLE)` làm placeholder.

### Bước 5 — Trace frontend render

```tsx
// DwellTab.tsx line 27
const p90Dwell = Math.max(...trend.map(item => item.p90_dwell_sec), 0)
// = Math.max(0.0, 0) = 0

// line 36
value={p90Dwell > 0 ? formatDuration(p90Dwell) : '—'}
// 0 > 0 = false → '—'
```

API trả về `0.0` (vì `_safe_float(None) = 0.0`) → frontend check `> 0` → hiện `'—'`.

---

## 3. Root Cause

```
Flink SQL (dwell_daily.sql)
  └─ CAST(NULL AS DOUBLE) AS p50_dwell_sec   ← Flink không có approx_percentile
  └─ CAST(NULL AS DOUBLE) AS p90_dwell_sec
       │
       ▼
gold_serving_dwell_daily (Iceberg)
  └─ p50 = NULL, p90 = NULL
       │
       ▼
analytics_queries.py → _safe_float(None) → 0.0
       │
       ▼
DwellTab.tsx → p90Dwell = 0 → '—'
```

Lưu ý: Legacy Trino SQL (`services/gold_serving/sql/refresh/dwell_daily.sql`) **đã có** `approx_percentile` nhưng không được dùng — hệ thống hiện chạy Flink batch path thay vì Trino path.

---

## 4. Hướng xử lí

### Option A — Route `dwell_daily` sang Trino (Khuyến nghị)

**Thay đổi:** `submit_batch_job.py` — thêm branch logic: nếu `domain == "dwell_daily"` → chạy Trino SQL thay vì upload JAR Flink.

```
submit_batch_job.py
  ├─ domain == "dwell_daily"  → _trino_run(dwell_daily.sql)   ← NEW PATH
  └─ domain == *              → upload JAR → Flink batch       ← existing
```

**File cần thay đổi:**
- `services/flink-jobs/python/submit_batch_job.py` — thêm Trino branch cho dwell domain
- `services/gold_serving/sql/refresh/dwell_daily.sql` — verify `approx_percentile` syntax đúng với Trino 468

**Pros:**
- SQL đã tồn tại và có `approx_percentile` chạy đúng trên Trino
- `_trino_run()` đã có sẵn trong `submit_batch_job.py`
- Thay đổi nhỏ nhất, không đụng Flink pipeline
- Airflow DAG không cần sửa

**Cons:**
- `dwell_daily` chạy khác pattern so với các domain khác (Trino vs Flink)

---

### Option B — Tính percentile on-the-fly trong analytics query

**Thay đổi:** `analytics_queries.py` — `dwell_trend_sql` JOIN thêm `gold_track_summary_v2` để tính p50/p90 trực tiếp qua Trino lúc query.

**Pros:** Không đụng pipeline, không sửa Flink/Airflow

**Cons:**
- Mỗi cold API call scan thêm `gold_track_summary_v2` (~5,800+ rows)
- Vi phạm serving layer pattern (analytics query bypass serving table)
- Latency tăng khi data lớn

---

### Option C — Thêm Trino enrichment task trong DAG

**Thay đổi:** DAG `gold_serving_dwell` thêm task 2 chạy Trino để DELETE + INSERT lại với p50/p90.

**Pros:** Tách bạch rõ từng bước

**Cons:**
- 2 lần write vào Iceberg cho cùng 1 date window
- Phức tạp hơn cần thiết

---

## 5. Files liên quan

| File | Vai trò |
|---|---|
| `services/flink-jobs/java/src/main/resources/dwell_daily.sql` | Flink batch SQL — source của NULL |
| `services/gold_serving/sql/refresh/dwell_daily.sql` | Legacy Trino SQL — có `approx_percentile` ✅ |
| `services/flink-jobs/python/submit_batch_job.py` | Orchestrator — cần thêm Trino branch |
| `infrastructure/airflow/dags/gold_serving_dwell.py` | Airflow DAG — không cần sửa |
| `services/api/src/rva_api/api/v1/analytics_queries.py` | `dwell_trend_sql` — đọc p50/p90 từ serving table |
| `frontend/src/features/analytics/components/tabs/DwellTab.tsx` | Render P90 Dwell card và Trend chart |
