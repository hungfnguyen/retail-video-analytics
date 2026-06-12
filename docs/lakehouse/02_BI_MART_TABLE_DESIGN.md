# BI Mart Table Design

Tài liệu này thiết kế các bảng mart cho tầng analyst. Mục tiêu là để dashboard query dữ liệu đã chuẩn bị sẵn, thay vì mỗi request phải aggregate lại từ `silver_detections_v2`.

## 1. Nguyên tắc thiết kế mart

### 1.1 Mart phải đi từ câu hỏi dashboard

Không thiết kế mart theo source table trước. Thiết kế theo câu hỏi:

- hôm nay có bao nhiêu visitor;
- traffic theo giờ thế nào;
- camera nào đông nhất;
- zone nào nóng nhất;
- heatmap 1 ngày/7 ngày ra sao;
- queue nào có wait time cao;
- alert nào xảy ra nhiều.

Sau đó mới chọn source Gold/Silver phù hợp.

### 1.2 Mart có grain rõ ràng

Mỗi bảng phải trả lời được:

```text
1 row đại diện cho cái gì?
```

Ví dụ:

| Bảng | Grain |
|---|---|
| `mart_traffic_hourly` | 1 store + 1 camera + 1 hour |
| `mart_heatmap_tile_5min` | 1 store + 1 camera + 1 5-minute bucket + 1 tile |
| `mart_queue_hourly` | 1 store + 1 camera + 1 queue zone + 1 hour |
| `mart_zone_daily` | 1 store + 1 camera + 1 zone + 1 day |

### 1.3 Mart không thay thế Gold

Gold là business aggregate tương đối generic. Mart là bảng phục vụ trực tiếp dashboard.

```text
Gold: reusable facts
Mart: screen-specific serving tables
```

### 1.4 Mart phải dễ refresh lại

Các mart nên refresh theo partition:

- intraday: refresh ngày hiện tại hoặc last N hours;
- daily: finalize ngày hôm qua;
- backfill: refresh date range.

### 1.5 Metric phải additive khi rollup — cảnh báo `COUNT(DISTINCT)`

> **Quan trọng (verified bug):** `unique_tracks` / `unique_visitors` tính bằng `COUNT(DISTINCT track_id)` **KHÔNG cộng được**. Rollup `mart_*_hourly → daily` hay `5min → hourly` bằng `SUM(unique_tracks)` sẽ **đếm trùng**: một track ở 2 bucket → +2; một visitor ở 3 ngày → "3 unique". Bug này đang tồn tại trong `analytics_queries.py` (`summary_sql` làm `SUM(daily.unique_tracks)` qua nhiều ngày).
>
> Mỗi mart phải khai báo rõ cột nào additive:
> - **Additive** (`SUM` an toàn): `detection_count`, `crossing_count`, `sessions`, `alert_count`, `occupied_minutes`.
> - **Non-additive** (KHÔNG `SUM` khi rollup): `unique_tracks`, `unique_visitors`, mọi `p50/p90/max`, `avg_*`.
>
> Với cột non-additive, chọn 1:
> 1. **Recompute từ base grain** — mỗi grain tự `COUNT(DISTINCT)` từ silver/gold thấp nhất, không roll từ mart cao hơn (đơn giản, đúng, hơi tốn compute).
> 2. **HLL sketch** — lưu cột `approx_set(track_id)` (Trino HyperLogLog), rollup bằng `merge()` rồi `cardinality()`. Cộng được, sai số ~2%.
> 3. **Chấp nhận & đổi tên** — giữ `SUM` nhưng đổi tên thành `visitor_appearances` / `track_day_count` (không gọi là "unique").
>
> Tương tự: `avg_*` phải tính lại từ `SUM(numerator)/SUM(denominator)`, không `AVG(avg_*)`; percentile phải tính từ raw, không roll từ percentile con.

## 2. Namespace

Khuyến nghị tạo schema riêng:

```sql
CREATE SCHEMA IF NOT EXISTS lakehouse.rva_mart;
```

Nếu muốn đơn giản cho dev/demo, có thể giữ trong `lakehouse.rva` với prefix `mart_`. Tuy nhiên schema riêng rõ hơn:

```text
lakehouse.rva       = Bronze/Silver/Gold foundation
lakehouse.rva_mart  = BI serving marts
```

## 3. Mart catalog tổng thể

| Dashboard | Mart chính | Source đề xuất |
|---|---|---|
| Executive Overview | `mart_executive_daily` | Gold camera/queue/alert tables |
| Traffic Analytics | `mart_traffic_hourly`, `mart_traffic_daily` | `gold_camera_hourly_metrics`, `gold_camera_daily_metrics` |
| Dwell Analytics | `mart_dwell_daily`, `mart_zone_dwell_daily` | `gold_track_summary_v2`, `gold_camera_daily_dwell` |
| Historical Heatmap | `mart_heatmap_tile_5min`, `mart_heatmap_tile_hour` | `silver_detections_v2` initially, later Gold heatmap |
| Zone Analytics | `mart_zone_hourly`, `mart_zone_daily` | `gold_zone_minute_metrics` |
| Queue Analytics | `mart_queue_hourly`, `mart_queue_daily` | `gold_queue_sessions` |
| Alert Analytics | `mart_alert_hourly`, `mart_alert_daily` | `gold_alert_events`, `gold_alerts` |
| Funnel/Line Crossing | `mart_line_crossing_hourly`, `mart_store_funnel_daily` | future `silver_line_crossings` / `gold_line_crossing_hourly` |

> **Lưu ý lineage:** `gold_camera_hourly_metrics` / `gold_camera_daily_metrics` / `gold_camera_daily_dwell` cuối cùng phái sinh từ **`silver_detections` v1** (qua `GoldDashboardAggregateJob`), trong khi heatmap/zone/queue đi từ **`silver_detections_v2`**. Khi xây mart traffic/dwell phải nhớ chúng phụ thuộc nhánh v1 — xem đính chính dual-lineage ở `01_AIRFLOW_ANALYST_ARCHITECTURE.md §8`.
>
> **Alert sources khác semantics:** `gold_alerts` đếm **clip incident**, `gold_alert_events` đếm **frame vượt ngưỡng density_high**. `mart_alert_*` phải chọn rõ đếm cái nào — không UNION/thay thế tùy tiện (xem `§10`).

## 4. Executive mart

### `mart_executive_daily`

Mục tiêu: một bảng nhỏ cho trang overview.

Grain:

```text
store_id + metric_date
```

Schema đề xuất:

```sql
CREATE TABLE IF NOT EXISTS lakehouse.rva_mart.mart_executive_daily (
    store_id VARCHAR,
    metric_date DATE,

    total_detections BIGINT,
    unique_visitors BIGINT,
    active_camera_count BIGINT,

    avg_dwell_sec DOUBLE,
    p50_dwell_sec DOUBLE,
    p90_dwell_sec DOUBLE,

    queue_sessions BIGINT,
    avg_queue_wait_sec DOUBLE,
    p90_queue_wait_sec DOUBLE,
    max_queue_wait_sec DOUBLE,

    total_alerts BIGINT,
    high_alerts BIGINT,
    latest_alert_ts TIMESTAMP(3),

    peak_hour INTEGER,
    peak_hour_detections BIGINT,

    source_min_ts TIMESTAMP(3),
    source_max_ts TIMESTAMP(3),
    refreshed_at TIMESTAMP(3)
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['metric_date']
);
```

Dashboard dùng bảng này cho:

- Visitors Today;
- Unique Tracks Today;
- Avg Dwell Time;
- Queue Avg Wait;
- Total Alerts;
- Peak Hour.

Refresh:

```text
Intraday: mỗi 15 phút cho ngày hiện tại.
Daily finalize: chạy lại ngày hôm qua lúc 01:00-02:00.
```

## 5. Traffic marts

### `mart_traffic_hourly`

Grain:

```text
store_id + camera_id + bucket_hour
```

Schema:

```sql
CREATE TABLE IF NOT EXISTS lakehouse.rva_mart.mart_traffic_hourly (
    store_id VARCHAR,
    camera_id VARCHAR,
    bucket_hour TIMESTAMP(3),
    metric_date DATE,
    hour_of_day INTEGER,

    detection_count BIGINT,
    unique_visitors BIGINT,
    avg_people_count DOUBLE,
    max_people_count BIGINT,

    avg_processing_fps DOUBLE,
    avg_inference_ms DOUBLE,
    avg_metadata_lag_ms DOUBLE,

    refreshed_at TIMESTAMP(3)
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['metric_date', 'bucket(16, camera_id)']
);
```

Source:

```text
gold_camera_hourly_metrics
```

API usage:

- traffic trend chart;
- camera comparison;
- peak hour analysis;
- operational quality chart.

### `mart_traffic_daily`

Grain:

```text
store_id + camera_id + metric_date
```

Source:

```text
gold_camera_daily_metrics
```

Dùng cho daily comparison và executive rollup.

## 6. Historical heatmap marts

Đây là phần nên ưu tiên vì historical heatmap hiện có nguy cơ query trực tiếp `silver_detections_v2`.

### `mart_heatmap_tile_5min`

Grain:

```text
store_id + camera_id + bucket_start + tile_x + tile_y
```

Schema:

```sql
CREATE TABLE IF NOT EXISTS lakehouse.rva_mart.mart_heatmap_tile_5min (
    store_id VARCHAR,
    camera_id VARCHAR,
    bucket_start TIMESTAMP(3),
    bucket_end TIMESTAMP(3),
    metric_date DATE,

    grid_width INTEGER,
    grid_height INTEGER,
    tile_x INTEGER,
    tile_y INTEGER,

    detection_count BIGINT,
    unique_tracks BIGINT,
    avg_conf DOUBLE,

    source_rows BIGINT,
    refreshed_at TIMESTAMP(3)
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['metric_date', 'bucket(16, camera_id)']
);
```

Transform logic — **phải clamp giống `heatmap_presence_sql` production** (norm=1.0 → index 32 ngoài lưới 0-31):

```sql
tile_x = LEAST(31, GREATEST(0, CAST(FLOOR(anchor_x_norm * 32) AS INTEGER)))
tile_y = LEAST(23, GREATEST(0, CAST(FLOOR(anchor_y_norm * 24) AS INTEGER)))
grid_width = 32
grid_height = 24
```

Filter source — **giữ y hệt query production để số khớp dashboard cũ**:

```sql
class_id = 0
is_predicted = false
anchor_x_norm IS NOT NULL
anchor_y_norm IS NOT NULL
```

> **KHÔNG** thêm `global_track_id IS NOT NULL` hoặc `anchor BETWEEN 0 AND 1` trừ khi sửa luôn `heatmap_presence_sql` cho khớp — nếu lệch filter, heatmap-từ-mart ra số khác heatmap hiện tại và migration không còn trong suốt. `unique_tracks` lưu dạng HLL (`approx_set(global_track_id)`), không phải `COUNT(DISTINCT)` rồi `SUM` (xem `§1.5`).

### `mart_heatmap_tile_hour`

Grain:

```text
store_id + camera_id + bucket_hour + tile_x + tile_y
```

Source:

```text
mart_heatmap_tile_5min
```

Lý do có thêm hourly:

- query 7d/14d/30d nhanh hơn;
- giảm số row API phải đọc;
- phù hợp UI historical heatmap.

Query dashboard:

```sql
SELECT
    tile_x,
    tile_y,
    SUM(detection_count) AS intensity   -- additive: OK
FROM lakehouse.rva_mart.mart_heatmap_tile_hour
WHERE camera_id = ?
  AND bucket_hour >= ?
  AND bucket_hour < ?
GROUP BY tile_x, tile_y;
```

> **Cảnh báo non-additive (xem `§1.5`):** **không** `SUM(unique_tracks)` khi rollup `5min → hour` hoặc khi query nhiều giờ — track nằm trên nhiều bucket sẽ bị đếm trùng. Heatmap intensity nên dùng `detection_count` (additive). Nếu cần unique tracks per tile theo range, hoặc dùng cột HLL `approx_set(track_id)` rồi `cardinality(merge(...))`, hoặc recompute trực tiếp từ `silver_detections_v2`. Vì lý do này, `mart_heatmap_tile_5min` nên lưu thêm cột HLL nếu muốn unique chính xác ở mọi grain.

## 7. Zone marts

### `mart_zone_hourly`

Grain:

```text
store_id + camera_id + zone_id + bucket_hour
```

Schema:

```sql
CREATE TABLE IF NOT EXISTS lakehouse.rva_mart.mart_zone_hourly (
    store_id VARCHAR,
    camera_id VARCHAR,
    zone_id VARCHAR,
    zone_type VARCHAR,
    bucket_hour TIMESTAMP(3),
    metric_date DATE,

    avg_occupancy DOUBLE,
    max_occupancy BIGINT,
    unique_visitors BIGINT,
    detection_count BIGINT,
    occupied_minutes BIGINT,

    refreshed_at TIMESTAMP(3)
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['metric_date', 'bucket(16, camera_id)']
);
```

Source:

```text
gold_zone_minute_metrics
```

Widgets:

- top zones by occupancy;
- zone trend;
- zone comparison table;
- store layout utilization.

### `mart_zone_daily`

Grain:

```text
store_id + camera_id + zone_id + metric_date
```

Source:

```text
mart_zone_hourly
```

## 8. Queue marts

### `mart_queue_hourly`

Grain:

```text
store_id + camera_id + queue_zone_id + bucket_hour
```

Schema:

```sql
CREATE TABLE IF NOT EXISTS lakehouse.rva_mart.mart_queue_hourly (
    store_id VARCHAR,
    camera_id VARCHAR,
    queue_zone_id VARCHAR,
    bucket_hour TIMESTAMP(3),
    metric_date DATE,

    sessions BIGINT,
    completed_sessions BIGINT,
    avg_wait_sec DOUBLE,
    p50_wait_sec DOUBLE,
    p90_wait_sec DOUBLE,
    max_wait_sec DOUBLE,
    avg_frame_count DOUBLE,

    sla_breach_count BIGINT,
    sla_threshold_sec INTEGER,

    refreshed_at TIMESTAMP(3)
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['metric_date', 'bucket(16, camera_id)']
);
```

Source:

```text
gold_queue_sessions
```

Business logic:

```text
SLA breach = wait_time_sec >= threshold, ví dụ 120s hoặc config theo zone.
```

### `mart_queue_daily`

Source:

```text
mart_queue_hourly
```

Widgets:

- average wait;
- worst queue zones;
- sessions by hour;
- queue SLA breach trend.

## 9. Dwell marts

### `mart_dwell_daily`

Grain:

```text
store_id + camera_id + metric_date
```

Schema:

```sql
CREATE TABLE IF NOT EXISTS lakehouse.rva_mart.mart_dwell_daily (
    store_id VARCHAR,
    camera_id VARCHAR,
    metric_date DATE,

    track_count BIGINT,
    avg_dwell_sec DOUBLE,
    p50_dwell_sec DOUBLE,
    p90_dwell_sec DOUBLE,
    max_dwell_sec DOUBLE,

    short_dwell_tracks BIGINT,
    medium_dwell_tracks BIGINT,
    long_dwell_tracks BIGINT,

    refreshed_at TIMESTAMP(3)
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['metric_date', 'bucket(16, camera_id)']
);
```

Source:

```text
gold_track_summary_v2
```

Suggested buckets:

```text
short:  < 30s
medium: 30s - 120s
long:   >= 120s
```

### `mart_zone_dwell_daily`

Future table. Cần zone transition/session data ổn hơn.

## 10. Alert marts

### `mart_alert_hourly`

Grain:

```text
store_id + camera_id + alert_type + bucket_hour
```

Schema:

```sql
CREATE TABLE IF NOT EXISTS lakehouse.rva_mart.mart_alert_hourly (
    store_id VARCHAR,
    camera_id VARCHAR,
    alert_type VARCHAR,
    severity VARCHAR,
    bucket_hour TIMESTAMP(3),
    metric_date DATE,

    alert_count BIGINT,
    acknowledged_count BIGINT,
    clip_count BIGINT,
    latest_alert_ts TIMESTAMP(3),

    refreshed_at TIMESTAMP(3)
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['metric_date', 'bucket(16, camera_id)']
);
```

Source:

```text
gold_alert_events   -- mỗi frame vượt ngưỡng density_high (từ silver_detections v1)
gold_alerts         -- clip incident (từ media-events / GoldAlertsJob)
```

> **Hai nguồn này đếm đơn vị KHÁC nhau** — `gold_alert_events` = số frame vượt ngưỡng, `gold_alerts` = số clip đã ghi. Không UNION trực tiếp. Quyết định rõ `mart_alert_*` đại diện cho cái gì:
> - Nếu muốn "số sự cố mật độ cao" → dùng `gold_alerts` (đã dedup theo incident/cooldown).
> - Nếu muốn "tần suất frame vượt ngưỡng" (raw signal) → dùng `gold_alert_events`, nhưng nên gắn nhãn `alert_type` rõ và **không** trộn vào cùng `alert_count` với clip.

### `mart_alert_daily`

Source:

```text
mart_alert_hourly
```

## 11. Funnel/line crossing marts

Hiện tại line crossing historical model chưa đủ rõ. Đây nên là phase sau.

Cần thêm source:

```text
silver_line_crossings
gold_line_crossing_hourly
```

Sau đó tạo:

```text
mart_line_crossing_hourly
mart_store_funnel_daily
```

Schema gợi ý:

```sql
CREATE TABLE IF NOT EXISTS lakehouse.rva_mart.mart_line_crossing_hourly (
    store_id VARCHAR,
    camera_id VARCHAR,
    line_id VARCHAR,
    line_type VARCHAR,
    direction VARCHAR,
    bucket_hour TIMESTAMP(3),
    metric_date DATE,

    crossing_count BIGINT,
    unique_tracks BIGINT,

    refreshed_at TIMESTAMP(3)
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['metric_date', 'bucket(16, camera_id)']
);
```

## 12. Audit tables

### `mart_refresh_audit`

Mỗi lần Airflow refresh mart, ghi một row audit.

```sql
CREATE TABLE IF NOT EXISTS lakehouse.rva_mart.mart_refresh_audit (
    dag_id VARCHAR,
    task_id VARCHAR,
    run_id VARCHAR,
    mart_table VARCHAR,
    partition_date DATE,
    refresh_window_start TIMESTAMP(3),
    refresh_window_end TIMESTAMP(3),

    source_table VARCHAR,
    source_min_ts TIMESTAMP(3),
    source_max_ts TIMESTAMP(3),
    source_row_count BIGINT,
    output_row_count BIGINT,

    status VARCHAR,
    error_message VARCHAR,
    started_at TIMESTAMP(3),
    finished_at TIMESTAMP(3),
    refreshed_at TIMESTAMP(3)
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['partition_date']
);
```

### `data_quality_results`

```sql
CREATE TABLE IF NOT EXISTS lakehouse.rva_mart.data_quality_results (
    dag_id VARCHAR,
    run_id VARCHAR,
    check_name VARCHAR,
    table_name VARCHAR,
    partition_date DATE,
    severity VARCHAR,
    status VARCHAR,
    observed_value VARCHAR,
    expected_rule VARCHAR,
    checked_at TIMESTAMP(3)
)
WITH (
    format = 'PARQUET',
    format_version = 2,
    partitioning = ARRAY['partition_date']
);
```

## 13. Ưu tiên triển khai marts

Thứ tự nên làm:

1. `mart_heatmap_tile_5min`
2. `mart_heatmap_tile_hour`
3. `mart_traffic_hourly`
4. `mart_queue_hourly`
5. `mart_zone_hourly`
6. `mart_executive_daily`
7. audit tables
8. alert/dwell/funnel marts

Lý do: heatmap là pain point rõ nhất vì hiện có thể query Silver. Traffic/queue/zone đã có Gold làm source nên mart dễ hơn.
