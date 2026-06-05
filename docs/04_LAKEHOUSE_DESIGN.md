# Lakehouse Design

## Technology

| Layer | Technology |
|---|---|
| Table format | Apache Iceberg |
| Catalog | Iceberg REST |
| Object storage | AWS S3 |
| Query engine | Trino |
| Writer | Flink |

## Current Namespace

All implemented tables are in:

```text
lakehouse.rva
```

## Current Tables

```text
lakehouse.rva.bronze_raw
lakehouse.rva.silver_detections
lakehouse.rva.gold_track_summary
lakehouse.rva.gold_camera_hourly_metrics
lakehouse.rva.gold_camera_daily_metrics
lakehouse.rva.gold_camera_daily_dwell
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

## Silver: `silver_detections`

Purpose: flatten one frame event into detection rows.

Important columns:

| Column | Notes |
|---|---|
| `event_id` | Link to Bronze event |
| `detection_id` | Detection-level id |
| `store_id`, `camera_id` | Query dimensions |
| `frame_index`, `capture_ts` | Frame time and sequence |
| `class_name`, `class_id`, `conf` | Detection semantics |
| `bbox_x1`, `bbox_y1`, `bbox_x2`, `bbox_y2` | Pixel bounding box |
| `track_id` | Camera/run scoped tracking id |
| `processing_ts` | Flink processing timestamp |

Quality rules:

- Required ids are non-null.
- `track_id` is required.
- `conf >= 0.4`.
- Deduplication uses `ROW_NUMBER()` by event and detection key.

Partitioning: `store_id`, `bucket(16, camera_id)`, `days(capture_ts)`.

## Gold: `gold_track_summary`

Purpose: aggregate track lifecycle from Silver rows.

Columns:

| Column | Notes |
|---|---|
| `store_id`, `camera_id` | Dimensions |
| `pipeline_run_id` | Run scope |
| `track_id` | Track key |
| `visit_date` | Date partition helper |
| `enter_ts` | First seen timestamp |
| `exit_ts` | Last seen timestamp |
| `duration_sec` | Track duration |
| `frames` | Distinct frames containing the track |

Primary key: `(store_id, camera_id, pipeline_run_id, track_id)` not enforced.

The table is configured with Iceberg format v2 and upsert enabled.

## Gold: Dashboard aggregate tables

Purpose: pre-aggregate dashboard metrics so FastAPI can query compact Gold tables instead of scanning Silver and track-level Gold tables on every Analytics page load.

### `gold_camera_hourly_metrics`

Hourly traffic metrics by store, camera, date, and hour:

| Column | Notes |
|---|---|
| `store_id`, `camera_id` | Query dimensions |
| `metric_date` | Date partition helper |
| `hour_of_day` | 0-23 local table hour |
| `detections` | Detection rows counted from Silver |
| `unique_tracks` | Distinct camera-scoped tracks in that hour |
| `avg_conf` | Average detection confidence |

Primary key: `(store_id, camera_id, metric_date, hour_of_day)` not enforced.

### `gold_camera_daily_metrics`

Daily camera quality and traffic metrics:

| Column | Notes |
|---|---|
| `store_id`, `camera_id` | Query dimensions |
| `metric_date` | Date partition helper |
| `detections` | Daily detection rows counted from Silver |
| `unique_tracks` | Distinct camera-scoped tracks |
| `avg_conf` | Weighted by Silver detections in downstream dashboard queries |
| `first_seen_ts`, `last_seen_ts` | Data coverage timestamps |

Primary key: `(store_id, camera_id, metric_date)` not enforced.

### `gold_camera_daily_dwell`

Daily camera dwell metrics from `gold_track_summary`:

| Column | Notes |
|---|---|
| `store_id`, `camera_id` | Query dimensions |
| `metric_date` | Date partition helper |
| `track_count` | Track rows in Gold |
| `avg_dwell_sec`, `total_dwell_sec` | Dwell duration metrics |
| `short_dwell_tracks` | Tracks shorter than 30 seconds |
| `long_dwell_tracks` | Tracks at least 120 seconds |

Primary key: `(store_id, camera_id, metric_date)` not enforced.

## Current Analytical Limits

The current Gold layer now includes dashboard aggregates for hourly traffic, daily camera metrics, and daily dwell metrics. It still does not include minute traffic, historical zone heatmap, alert history, or export-specific drill-down tables.

## Query Examples

```sql
SELECT COUNT(*) FROM lakehouse.rva.bronze_raw;

SELECT camera_id, COUNT(*) AS detections
FROM lakehouse.rva.silver_detections
GROUP BY camera_id;

SELECT camera_id, COUNT(*) AS tracks, AVG(duration_sec) AS avg_duration_sec
FROM lakehouse.rva.gold_track_summary
GROUP BY camera_id;
```

## Backfill Direction

Backfill should start from Bronze because it keeps the raw payload. A safe backfill plan is:

1. Select a time/camera range in `bronze_raw`.
2. Rebuild Silver into a staging table.
3. Validate counts and quality rules.
4. Rebuild affected Gold track summaries.
5. Swap or overwrite affected partitions.
