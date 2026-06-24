# Issue: Dashboard dùng detection_count thay vì unique_tracks cho nhiều metrics

**Ngày phát hiện:** 2026-06-24  
**Mức độ:** High — số liệu hiển thị sai nghĩa, gây nhầm lẫn nghiêm trọng  
**Status:** Root cause xác định, chưa fix

---

## 1. Triệu chứng

Dashboard Analytics hiện các số bất thường và mâu thuẫn nhau:

| Metric | Giá trị hiển thị | Kỳ vọng |
|---|---|---|
| Total Visitors | 7,586 | ✅ hợp lý |
| Peak Day (Jun 21) | 5,816 visitors | ✅ hợp lý |
| **Peak Hour (15:00)** | **332,131 visitors** | ❌ vô lý — 1 siêu thị nhỏ |
| **Top Zones (aisle 01)** | **43,259 visitors** | ❌ vô lý |
| Visitors by Day of Week | ~5,000–6,000 | ❌ thực ra là detection events |

---

## 2. Root Cause

Hệ thống dùng **hai định nghĩa "visitors" khác nhau** trong cùng 1 dashboard:

### detection_count ≠ người

```
detection_count = tổng số lần YOLO detect được người qua các frame
                = số_frame × số_người_trong_frame
                ≈ 25 fps × 4 người × 3600 giây = ~360,000/giờ
```

`detection_count` là **frame-level detection events**, không phải unique persons.

### Mapping thực tế từng metric

| Metric | SQL function | Nguồn | Column | Thực chất |
|---|---|---|---|---|
| Total Visitors | `summary_sql()` | `gold_serving_dwell_daily` | `track_count` | Unique `global_track_id` ✅ |
| Visitors Over Time | `visitors_series_sql()` | `gold_serving_dwell_daily` | `track_count` | Unique tracks ✅ |
| Peak Hour visitors | `hourly_sql()` | `gold_serving_traffic_hourly` | `detection_count` | Detection events ❌ |
| Visitors by Day of Week | `weekday_pattern_sql()` | `gold_serving_traffic_daily` | `detection_count` | Detection events ❌ |
| Top Zones visitors | `top_zones_sql()` | `gold_serving_zone_daily` | `detection_count` | Detection events ❌ |
| Peak Hours heatmap | `peak_heatmap_sql()` | `gold_serving_traffic_hourly` | `detection_count` | Detection events ❌ |

### Tại sao serving tables không có unique_tracks?

DDL `gold_serving_traffic_hourly` và `gold_serving_zone_daily` không có cột `unique_tracks`:

```sql
-- gold_serving_traffic_hourly
CREATE TABLE gold_serving_traffic_hourly (
  detection_count  BIGINT,    -- ← frame-level events
  avg_people_count DOUBLE,    -- avg persons per frame (avg occupancy)
  max_people_count BIGINT,
  avg_conf         DOUBLE
  -- unique_tracks: KHÔNG CÓ
)

-- gold_serving_zone_daily
CREATE TABLE gold_serving_zone_daily (
  detection_count  BIGINT,    -- ← frame-level events
  avg_occupancy    DOUBLE,
  max_occupancy    BIGINT,
  occupied_minutes BIGINT
  -- unique_tracks: KHÔNG CÓ
)
```

Batch SQL `traffic_hourly.sql` tính detection_count từ frame aggregation:
```sql
COUNT(*) AS frame_det           -- đếm detections per frame slot
SUM(frame_det) AS detection_count  -- roll up → vẫn là detection events
```

Nguồn dữ liệu cho unique tracks (`gold_track_summary_v2`) chỉ có granularity **daily** (visit_date), không có hourly → không thể dùng cho Peak Hour breakdown.

---

## 3. Hệ quả

Con số trên dashboard **không nhất quán về đơn vị**:

```
Peak Day: 5,816 "visitors"  ← thực ra là unique tracks (đúng)
Peak Hour: 332,131 "visitors" ← thực ra là detection events (sai × 57 lần)

332,131 / 5,816 = 57 → như nói "1 giờ peak có 57x traffic của cả ngày" — vô lý
```

Ảnh hưởng:
- Gây nhầm lẫn khi đọc báo cáo
- "Top Zones" hiện sai thứ hạng nếu 2 zone có density khác nhau nhưng area giống nhau
- "Visitors by Day of Week" chart không so sánh được với "Total Visitors" KPI

---

## 4. Hướng xử lí

### Option A — Đổi label thành "Detections" thay vì "Visitors" (Nhanh nhất)

Chỉ sửa frontend label:
- "Peak Hour: 332,131 **visitors**" → "Peak Hour: 332,131 **detections**"
- "Top Zones: 43,259 **visitors**" → "43,259 **detections**"

Không cần thay đổi pipeline. Phù hợp để demo nhanh nhưng không fix business logic.

**File cần sửa:** `frontend/src/features/analytics/`

---

### Option B — Thêm `unique_tracks` vào traffic/zone serving tables (Đúng nhất)

Thêm cột `unique_tracks` vào DDL và batch SQL:

```sql
-- Thêm vào gold_serving_traffic_daily
unique_tracks BIGINT,   -- COUNT(DISTINCT global_track_id) per day

-- Thêm vào gold_serving_traffic_hourly  
unique_tracks BIGINT,   -- COUNT(DISTINCT global_track_id) per hour

-- Thêm vào gold_serving_zone_daily
unique_visitors BIGINT, -- COUNT(DISTINCT global_track_id) per zone per day
```

Source data: `silver_detections_v2` có `global_track_id` → dùng `COUNT(DISTINCT global_track_id)` trong batch SQL.

Sau đó sửa queries:
- `hourly_sql()` → dùng `unique_tracks` thay `detection_count` cho peak_row
- `top_zones_sql()` → dùng `unique_visitors` thay `detection_count`
- `weekday_pattern_sql()` → dùng `unique_tracks` thay `detection_count`

**Files cần sửa:**
- `services/gold_serving/sql/ddl/gold_serving.sql` — thêm cột
- `services/flink-jobs/java/src/main/resources/sql/gold-serving/traffic_hourly.sql`
- `services/flink-jobs/java/src/main/resources/sql/gold-serving/traffic_daily.sql`
- `services/flink-jobs/java/src/main/resources/sql/gold-serving/zone_daily.sql`
- `services/api/src/rva_api/api/v1/analytics_queries.py`
- Frontend labels

**Cons:** Cần rebuild JAR, re-apply DDL, re-run Airflow DAGs để backfill.

---

### Option C — Dùng `avg_people_count` × thời gian để ước tính (Tradeoff)

`avg_people_count` trong traffic_hourly = trung bình số người visible mỗi frame (≈ occupancy). Không phải unique visitors nhưng gần với "average occupancy per hour" — có ý nghĩa business hơn raw detection_count.

**Không khuyến nghị** — vẫn không phải "unique visitors".

---

## 5. Files liên quan

| File | Vai trò |
|---|---|
| `services/gold_serving/sql/ddl/gold_serving.sql` | DDL — thiếu `unique_tracks` trong traffic/zone tables |
| `services/flink-jobs/java/src/main/resources/sql/gold-serving/traffic_hourly.sql` | Batch SQL — dùng `COUNT(*)` frame-level |
| `services/flink-jobs/java/src/main/resources/sql/gold-serving/zone_daily.sql` | Batch SQL — tương tự |
| `services/api/src/rva_api/api/v1/analytics_queries.py` | `hourly_sql`, `top_zones_sql`, `weekday_pattern_sql` — dùng `detection_count` |
| `frontend/src/features/analytics/` | Label "visitors" cho các metric sai |
