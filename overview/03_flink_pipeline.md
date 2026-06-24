# Flink Pipeline — Stream Processing

## 1. Tổng quan

Flink xử lý stream dữ liệu từ Pulsar, viết vào Iceberg trên S3. Có 9 Flink jobs, chia làm 3 nhóm:

| Nhóm | Jobs | Mô tả |
|---|---|---|
| Core stream | BronzeIngestJob, SilverJob, RealtimeMetricsJob | Raw ingestion + enrichment + realtime state |
| Gold facts | GoldTrackSummaryJob, QueueAnalyticsJob, GoldDashboardAggregateJob, GoldAlertsJob | Business aggregations |
| Serving batch | GoldServingBatchJob | Refresh Gold Serving tables |

**Vị trí code:** `services/flink-jobs/java/src/main/java/org/rva/`

**Checkpoint:** 60 giây, EXACTLY_ONCE (Iceberg 2-phase commit)

## 2. BronzeIngestJob

**Source:** Pulsar `persistent://retail/metadata/events`
**Sink:** `lakehouse.rva.bronze_raw` (Iceberg)

**Chức năng:** Nhận raw JSON event, extract trường cơ bản, ghi nguyên payload để replay/audit.

**Schema `bronze_raw`:**
```sql
CREATE TABLE bronze_raw (
  schema_version    STRING,
  event_id          STRING,
  pipeline_run_id   STRING,
  frame_index       BIGINT,
  payload           STRING,   -- full JSON event, không mất dữ liệu
  camera_id         STRING,   -- extracted từ source.camera_id
  store_id          STRING,   -- extracted từ source.store_id
  ingest_ts         TIMESTAMP(6)
) PARTITIONED BY (store_id)
```

**Partitioning:** `store_id` — đủ granular cho demo 1 store.

## 3. SilverJob

**Source:** `lakehouse.rva.bronze_raw` (Iceberg streaming read)
**Sink:** `lakehouse.rva.silver_detections_v2` (Iceberg)

**Chức năng:** Flatten 1 frame event (1 row) thành N detection rows (1 row / person / frame). Áp dụng quality rules.

**UDTF `ParseDetections`:** Java UDTF nhận `payload` JSON → emit 1 row per detection.

**Quality rules được áp dụng:**
- `event_id`, `camera_id`, `store_id`, `global_track_id` phải non-null
- `conf >= 0.15`
- Deduplication bằng `ROW_NUMBER()` OVER (PARTITION BY event_id, detection_id)

**Schema key columns (`silver_detections_v2`):**
```sql
event_id, detection_id           -- identity
store_id, camera_id              -- dimensions
frame_index, capture_ts          -- time
conf, class_name                 -- detection quality
track_id, global_track_id        -- tracking identity
bbox_x1/y1/x2/y2                -- bounding box pixels
anchor_x_norm, anchor_y_norm    -- normalized anchor (bottom_center)
primary_zone_id, primary_zone_type  -- zone assignment
in_queue, queue_zone_id          -- queue state
processing_ts                    -- Flink processing time
```

**Partitioning:** `store_id`, `bucket(16, camera_id)`, `days(capture_ts)` — tối ưu filter theo ngày.

## 4. RealtimeMetricsJob

**Source:** Pulsar `persistent://retail/metadata/events`
**Sink:** Redis

**Chức năng:** Pipeline latency thấp nhất — không qua Iceberg, ghi thẳng vào Redis.

**Ghi các Redis keys:**
```
stats:count:{camera_id}           ← tổng detections trong frame
live:frame:{camera_id}            ← full frame JSON (freshness indicator)
heatmap:live:{camera_id}          ← ZINCRBY theo grid cell (64×48)
track:active:{camera_id}:{gid}    ← HSET bbox, zone, conf, last_seen
zone:count:{camera_id}            ← HSET per zone_id
queue:live:{camera_id}:{zone_id}  ← wait_ms, avg_wait_ms, max_wait_ms
```

**Alert density:** khi count >= `ALERT_DENSITY_THRESHOLD` → ghi `gold_alert_events` record.

## 5. GoldTrackSummaryJob

**Source:** `lakehouse.rva.silver_detections_v2`
**Sink:** `lakehouse.rva.gold_track_summary_v2`

**Grain:** `store_id + camera_id + pipeline_run_id + global_track_id` (1 row / unique person / run)

**Aggregations:**
```sql
MIN(capture_ts) AS first_seen_ts
MAX(capture_ts) AS last_seen_ts
COUNT(*) AS frame_count
MAX(conf) AS max_conf
AVG(conf) AS avg_conf
LAST_VALUE(primary_zone_id) AS last_zone_id
```

**Dùng cho:** Dwell analytics — tính thời gian ở lại của từng khách (last_seen - first_seen), phân loại dwell band (short/medium/long).

## 6. QueueAnalyticsJob

**Source:** `lakehouse.rva.silver_detections_v2` (filter `in_queue = true`)
**Sink:** `lakehouse.rva.gold_queue_sessions`

**Grain:** `store_id + camera_id + queue_zone_id + global_track_id` (1 row / person / queue zone)

**Aggregations:**
```sql
MIN(capture_ts) AS enter_ts
MAX(capture_ts) AS exit_ts
TIMESTAMPDIFF(SECOND, enter_ts, exit_ts) AS wait_sec
```

**Dùng cho:** Queue analytics — tính thời gian chờ thực của từng người tại quầy.

## 7. GoldDashboardAggregateJob

**Source:** `silver_detections_v2` + `gold_track_summary_v2`
**Sinks:** 4 Gold fact tables:

```
gold_camera_hourly_metrics   ← detection_count, unique_tracks theo giờ/camera
gold_camera_daily_metrics    ← detection_count, unique_tracks theo ngày/camera
gold_camera_daily_dwell      ← track_count theo dwell band (short/medium/long)
gold_alert_events            ← frame-level density signal (KHÔNG phải alert incidents)
```

**Lưu ý:** `gold_alert_events` ≠ `gold_alerts`. `gold_alert_events` là signal density per-frame, còn `gold_alerts` là clip-backed incidents.

## 8. GoldAlertsJob

**Source:** Pulsar `persistent://retail/metadata/media-events`
**Sink:** `lakehouse.rva.gold_alerts`

**Chức năng:** Nhận `clip_created` events từ Vision clip extractor → ghi alert incidents có kèm S3 clip key.

**Schema `gold_alerts`:**
```sql
alert_id       STRING,
camera_id      STRING,
store_id       STRING,
alert_type     STRING,   -- density_high, queue_overcrowded, long_wait
severity       STRING,   -- high, medium, low
trigger_ts     TIMESTAMP,
clip_s3_key    STRING,   -- S3 path của video clip
clip_duration_sec DOUBLE
```

## 9. Gold Serving Refresh (Airflow + Trino SQL)

**Vị trí:** `services/gold_serving/sql/refresh/` + `infrastructure/airflow/dags/`

**12 Gold Serving tables, mỗi table có 1 DAG refresh:**

| DAG | Bảng | Schedule |
|---|---|---|
| gold_serving_traffic | traffic_hourly, traffic_daily | @daily |
| gold_serving_heatmap | heatmap_tile_5min, heatmap_tile_hour | @hourly |
| gold_serving_queue | queue_hourly, queue_daily | @daily |
| gold_serving_zone | zone_hourly, zone_daily | @daily |
| gold_serving_dwell | dwell_daily | @daily |
| gold_serving_executive | executive_daily | @daily |
| gold_serving_alert | alert_hourly, alert_daily | @daily |
| gold_serving_today_refresh | tất cả today partitions | @hourly |
| gold_quality_checks | quality assertions | @daily |
| iceberg_maintenance | EXPIRE SNAPSHOTS + REWRITE FILES | @weekly |

**Refresh engine:** Trino SQL `INSERT OVERWRITE` vào Iceberg partition.

**Physical schema:**
```
lakehouse.rva_gold_serving.gold_serving_traffic_daily
lakehouse.rva_gold_serving.gold_serving_dwell_daily
lakehouse.rva_gold_serving.gold_serving_queue_daily
... (12 tables tổng cộng)
```

## 10. Iceberg Configuration

```
Catalog type: REST
Catalog URI: http://iceberg-rest:8181
Warehouse: s3a://s3-retail-video-analytics/lakehouse
Backend catalog storage: PostgreSQL (lakehouse.rva_gold_serving schema)
File format: Parquet
Compression: ZSTD
Checkpoint: 60s EXACTLY_ONCE
```

**Catalog persistence:** Postgres JDBC → data không mất khi restart container (đã fix lỗi SQLite in-memory trước đó).
