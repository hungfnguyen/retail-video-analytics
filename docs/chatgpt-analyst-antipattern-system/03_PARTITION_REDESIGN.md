# Partition Redesign — quyết định theo scope đồ án

Tài liệu này chốt lại: trong các đề xuất partition của `partition-strateric.md`, **cái nào
sửa thật trong đồ án**, **cái nào để Future Work**, và **cái nào nói quá**. Kèm DDL đề xuất.

> Bối cảnh: dữ liệu hiện tại là demo/thesis (≈1 store, ít camera, volume nhỏ). Phần lớn "vấn
> đề partition" chỉ phát tác khi multi-store + BI thật. Vì vậy nguyên tắc: **chỉ sửa cái rẻ
> + đúng hướng + có lợi ngay cho BI/UI**, còn lại version-hoá (v2/v3) như Future Work để
> tránh phá pipeline đang chạy ổn.

---

## 1. Hiện trạng partition (đã verify)

| Bảng | Partition hiện tại | Nguồn |
|---|---|---|
| `bronze_raw` | `store_id` (không có cột ngày) | `BronzeIngestJob.java:60,86` |
| `silver_detections_v2` | `store_id,bucket(16,camera_id),days(capture_ts)` | `SilverJob.java:93` |
| `gold_track_summary_v2` | `store_id,bucket(16,camera_id),days(visit_date)` | `GoldTrackSummaryJob.java:68` |
| `gold_queue_sessions` | `store_id,bucket(16,camera_id),days(visit_date)` | `QueueAnalyticsJob.java:72` |
| `gold_alerts` | `days(event_ts)` | `GoldAlertsJob.java:70` |
| `gold_serving_*` (12 bảng) | `metric_date,bucket(16,camera_id)` | `GoldServingSupport.java` |
| `gold_serving_executive_daily` | `metric_date` | `GoldServingSupport.java:262` |
| `gold_serving_refresh_audit` / `_data_quality_results` | `partition_date` | `GoldServingSupport.java:323,342` |

---

## 2. Phân loại đánh giá của ChatGPT

### 2.1 Đúng & đáng sửa
1. **Serving tables thiếu `store_id` trong partition.** UI filter business đầu tiên là Store.
   `metric_date,bucket(16,camera_id)` không có store_id, và `bucket(16,camera_id)` trên bảng
   **daily nhỏ** tạo nhiều file nhỏ.
2. **`gold_alerts` partition `days(event_ts)`** trong khi query Alerts theo store/date.
3. **Chưa có `business_date` theo timezone store** — đây là điểm correctness cho retail BI
   (KPI "Today/Yesterday" theo local date).

### 2.2 Nói quá / giảm nhẹ
- **Bronze "antipattern lớn nhất":** nói quá. Bronze hiện chỉ bị Silver đọc streaming
  incremental, **không** query theo ngày ⇒ debt tiềm ẩn (xem `01_*` C2).
- **`days(capture_ts)` prune kém:** hơi quá với Trino (transform pushdown hoạt động). Vấn đề
  thật là timezone, không phải `days()` (xem `01_*` C4).
- **"Partition không gắn `{{ ds }}`":** nói quá — serving **đã** partition `metric_date` khớp
  `{{ ds }}` (xem `01_*` C7).

### 2.3 Sai về effort/scope
- Đề xuất tạo loạt bảng mới (`heatmap_cell_hourly`, `zone_spatial_daily`,
  `silver_detections_v3`, `bronze_raw_v2`...) + migration 5 phase: **đúng về lý thuyết nhưng
  over-scope cho đồ án**, và mâu thuẫn tinh thần "lean" đã chốt. ⇒ Future Work.

---

## 3. Quyết định cho đồ án

### Làm trong đồ án (rẻ, lợi ngay, ít rủi ro)

**Đ1. Thêm `store_id` vào partition các serving table** (đây là phần lợi nhất cho UI).
- Đổi `metric_date,bucket(16,camera_id)` → **`metric_date,store_id`** cho các bảng **aggregate
  nhỏ** (traffic/queue/zone/dwell/alert hourly+daily). Bỏ bucket camera ở bảng daily.
- Giữ `bucket(16,camera_id)` **chỉ** ở bảng high-volume: `heatmap_tile_5min`,
  `heatmap_tile_hour` → thành **`metric_date,store_id,bucket(16,camera_id)`**.
- `executive_daily`: `metric_date` → **`metric_date,store_id`**.
- **Lưu ý kỹ thuật:** đổi partition spec của bảng Iceberg đang tồn tại = thay đổi schema
  partition. An toàn nhất với đồ án: **drop & recreate** schema `rva_gold_serving` rồi backfill
  lại bằng Airflow (data nhỏ, backfill nhanh) — vì serving là dẫn xuất, không phải source of
  truth. (Phù hợp ghi chú memory: DDL re-apply sau restart.)

**Đ2. `gold_alerts`: `days(event_ts)` → `event_date,store_id`** (cột `event_date` đã có sẵn,
  `GoldAlertsJob.java:104`). Recreate bảng + để `GoldAlertsJob` ghi lại (upsert, volume nhỏ).

**Đ3. Bổ sung `business_date` (mức tối thiểu, đúng cho BI):**
- Trong Silver, thêm cột `business_date DATE` = `CAST(capture_ts AS DATE)` **theo timezone
  store** (cấu hình 1 timezone mặc định cho demo, vd `Australia/Sydney`, qua env).
- Các serving SQL derive `metric_date` từ `business_date` thay vì UTC `capture_ts`.
- Đây là thay đổi nhỏ nhưng giải quyết đúng vấn đề "Today/Yesterday lệch ngày". Nếu thời gian
  hạn chế: chỉ **ghi nhận giả định "1 store, 1 timezone, business_date = UTC date"** trong luận
  văn và để cột `business_date` cho v-next.

### Để Future Work (ghi luận văn, không code)
- `bronze_raw_v2` có `business_date,store_id,bucket(camera_id)`.
- `silver_detections_v3` partition theo `business_date,store_id,bucket(16,camera_id)`.
- Bảng mới `gold_serving_heatmap_cell_hourly`, `gold_serving_zone_spatial_daily` cho insight
  Heatmap/Zone (Top Hotspots, Zone Contribution).
- Migration 5 phase (v2/v3 song song → backfill → switch API → deprecate).

---

## 4. Partition matrix mục tiêu (sau Đ1–Đ2)

| Bảng | Partition mục tiêu | Ghi chú |
|---|---|---|
| `silver_detections_v2` | giữ `store_id,bucket(16,camera_id),days(capture_ts)` | đã ổn; chỉ thêm cột `business_date` (Đ3) |
| `gold_serving_traffic_hourly/daily` | `metric_date,store_id` | bỏ bucket camera |
| `gold_serving_queue_hourly/daily` | `metric_date,store_id` | zone là sort key, không partition |
| `gold_serving_zone_hourly/daily` | `metric_date,store_id` | zone là sort key |
| `gold_serving_dwell_daily` | `metric_date,store_id` | |
| `gold_serving_alert_hourly/daily` | `metric_date,store_id` | severity/type là sort key |
| `gold_serving_executive_daily` | `metric_date,store_id` | |
| `gold_serving_heatmap_tile_5min/hour` | `metric_date,store_id,bucket(16,camera_id)` | high-volume, giữ bucket |
| `gold_alerts` | `event_date,store_id` | cột sẵn có |
| `gold_serving_refresh_audit`/`_data_quality_results` | `partition_date` | giữ nguyên |

**Quy tắc nhớ nhanh:**
```
Serving aggregate (nhỏ):   metric_date + store_id            (zone/severity = sort key)
Heatmap tile (lớn):        metric_date + store_id + bucket(camera_id)
Alerts:                    event_date + store_id
Silver (fact lớn):         (giữ nguyên) + thêm cột business_date
Bronze:                    Future Work (thêm business_date)
```

---

## 5. DDL concept (cho phần làm trong đồ án)

Sửa trong `GoldServingSupport.ensureServingTables` (`GoldServingSupport.java:53-345`) — đổi
chuỗi `'partitioning'` tương ứng. Ví dụ traffic_daily:

```sql
CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_traffic_daily (
  store_id STRING, camera_id STRING, metric_date DATE,
  detection_count BIGINT, avg_people_count DOUBLE, max_people_count BIGINT,
  avg_conf DOUBLE, peak_hour INT, peak_hour_detections BIGINT,
  refreshed_at TIMESTAMP(6)
) WITH (
  'format-version' = '2',
  'write.format.default' = 'parquet',
  'partitioning' = 'metric_date,store_id'        -- (was: metric_date,bucket(16,camera_id))
);
```

heatmap_tile_5min (giữ bucket vì high-volume):
```sql
'partitioning' = 'metric_date,store_id,bucket(16,camera_id)'   -- thêm store_id
```

`gold_alerts` (sửa trong `GoldAlertsJob.java:70`):
```sql
'partitioning' = 'event_date,store_id'                          -- (was: days(event_ts))
```

> Sau khi đổi spec: drop schema `rva_gold_serving` (+ recreate `gold_alerts`) rồi backfill
> bằng Airflow `gold_serving_*` (catchup) cho range ngày demo. Vì serving/alerts là dẫn xuất,
> backfill lại an toàn và nhanh với data nhỏ.

---

## 6. Tác động tới API/UI (khớp `docs/ui/rva-ui-refactor-docs`)

Sau Đ1–Đ2, query BI map thẳng xuống partition:
```sql
WHERE metric_date BETWEEN :start_date AND :end_date
  AND store_id = :store_id
  -- camera_id / zone_id / severity: filter/sort phụ
```
Khuyến nghị API: chuyển param từ `days=N` sang `store_id + start_date + end_date
(+ camera_id/zone_id/layer)` để pruning đúng partition `metric_date,store_id`. Đây là **P1/P2
phía API** — chỉ làm khi UI refactor cần; không bắt buộc cùng đợt sửa partition.
