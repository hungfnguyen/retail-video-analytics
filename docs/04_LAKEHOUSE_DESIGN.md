# Lakehouse Design

## Technology

| Layer | Technology |
|---|---|
| Table format | Apache Iceberg |
| Catalog | Iceberg REST |
| Object storage | AWS S3 |
| Query engine | Trino |
| Streaming writer | Flink |
| Serving refresh engine | Trino SQL runner currently; Flink batch only when justified |

## Namespaces

Current logical namespaces:

```text
lakehouse.rva                 Bronze / Silver / Gold facts
lakehouse.rva_gold_serving    Gold serving tables
```

`rva_gold_serving` is a physical namespace for query-ready Gold tables. It is not a fourth medallion tier.

## Current Tables

Bronze / Silver / Gold facts:

```text
lakehouse.rva.bronze_raw
lakehouse.rva.silver_detections_v2
lakehouse.rva.gold_track_summary_v2
lakehouse.rva.gold_queue_sessions
lakehouse.rva.gold_camera_hourly_metrics
lakehouse.rva.gold_camera_daily_metrics
lakehouse.rva.gold_camera_daily_dwell
lakehouse.rva.gold_alert_events
lakehouse.rva.gold_alerts
```

Gold serving:

```text
lakehouse.rva_gold_serving.gold_serving_traffic_hourly
lakehouse.rva_gold_serving.gold_serving_traffic_daily
lakehouse.rva_gold_serving.gold_serving_heatmap_tile_5min
lakehouse.rva_gold_serving.gold_serving_heatmap_tile_hour
lakehouse.rva_gold_serving.gold_serving_queue_hourly
lakehouse.rva_gold_serving.gold_serving_queue_daily
lakehouse.rva_gold_serving.gold_serving_zone_hourly
lakehouse.rva_gold_serving.gold_serving_zone_daily
lakehouse.rva_gold_serving.gold_serving_dwell_daily
lakehouse.rva_gold_serving.gold_serving_executive_daily
lakehouse.rva_gold_serving.gold_serving_alert_hourly
lakehouse.rva_gold_serving.gold_serving_alert_daily
```

## Bronze: `bronze_raw`

Purpose: keep raw detection frame events for audit and replay.

Columns implemented by `BronzeIngestJob`:

| Column | Type | Notes |
|---|---|---|
| `schema_version` | string | Event schema version |
| `event_id` | string | Frame event id |
| `pipeline_run_id` | string | Vision run id |
| `frame_index` | bigint | Frame number |
| `payload` | string | Full raw JSON event |
| `camera_id` | string | Extracted from `source.camera_id` |
| `store_id` | string | Extracted from `source.store_id` |
| `ingest_ts` | timestamp | Flink processing timestamp |

Partitioning: `store_id`.

## Silver: `silver_detections_v2`

Purpose: flatten one frame event into enriched detection rows.

Important columns:

| Column | Notes |
|---|---|
| `event_id`, `detection_id` | Event and detection identifiers |
| `store_id`, `camera_id` | Query dimensions |
| `frame_index`, `source_frame_index`, `capture_ts` | Frame time and sequence |
| `class_name`, `class_id`, `conf` | Detection semantics |
| `bbox_x1`, `bbox_y1`, `bbox_x2`, `bbox_y2` | Pixel bounding box |
| `track_id`, `raw_track_id`, `global_track_id` | Tracking identities |
| `track_state`, `is_predicted` | Tracking state |
| `anchor_type`, `anchor_x`, `anchor_y`, `anchor_x_norm`, `anchor_y_norm` | Bottom-center / analytics anchor |
| `primary_zone_id`, `primary_zone_type` | Zone assignment |
| `in_queue`, `queue_zone_id` | Queue assignment |
| `model_name`, `detector_type`, `tracker_type` | Vision runtime metadata |
| `processing_ts` | Flink processing timestamp |

Quality rules:

- Required ids are non-null.
- `track_id` and `global_track_id` are required.
- `conf >= 0.15` in current lakehouse Silver v2 job.
- Deduplication uses `ROW_NUMBER()` by event and detection key.

Partitioning: `store_id`, `bucket(16, camera_id)`, `days(capture_ts)`.

## Gold Facts

### `gold_track_summary_v2`

Purpose: aggregate global track lifecycle from `silver_detections_v2`.

Grain:

```text
store_id + camera_id + pipeline_run_id + global_track_id
```

Used for dwell and visit lifecycle analytics.

### `gold_queue_sessions`

Purpose: aggregate queue wait sessions from queue detections in `silver_detections_v2`.

Grain:

```text
store_id + camera_id + queue_zone_id + global_track_id
```

Used by queue analytics and Gold serving queue tables.

### Dashboard Gold facts

`GoldDashboardAggregateJob` writes:

```text
gold_camera_hourly_metrics
gold_camera_daily_metrics
gold_camera_daily_dwell
gold_alert_events
```

Important:

- `gold_alert_events` is a frame-level density signal table.
- It is not the same as `gold_alerts`.

### `gold_alerts`

Purpose: clip-backed alert incident history from `media-events`.

Written by `GoldAlertsJob`.

Used by:

- alert history API
- `gold_serving_alert_hourly`
- `gold_serving_alert_daily`

## Gold Serving

Gold serving tables are query-ready tables for analyst dashboards.

Implementation currently lives in:

```text
services/gold_serving/
```

Physical schema:

```text
lakehouse.rva_gold_serving
```

Current refresh engine:

```text
Trino SQL runner
```

Airflow skeleton can orchestrate refresh and maintenance, but Airflow is not the transform engine.

## Query Examples

```sql
SELECT COUNT(*) FROM lakehouse.rva.bronze_raw;

SELECT camera_id, COUNT(*) AS detections
FROM lakehouse.rva.silver_detections_v2
GROUP BY camera_id;

SELECT camera_id, COUNT(*) AS tracks, AVG(duration_sec) AS avg_duration_sec
FROM lakehouse.rva.gold_track_summary_v2
GROUP BY camera_id;

SHOW TABLES FROM lakehouse.rva_gold_serving;
```

## Backfill Direction

Backfill should start from Bronze because it keeps the raw payload.

Safe direction:

1. Select a time/camera range in `bronze_raw`.
2. Rebuild Silver v2 into a staging table or bounded job output.
3. Validate counts and quality rules.
4. Rebuild affected Gold facts.
5. Refresh affected Gold serving partitions.
6. Run Iceberg maintenance only with safe retention.
