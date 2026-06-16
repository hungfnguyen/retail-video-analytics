-- rva_gold_serving — Gold serving tables (Trino Iceberg DDL).
-- Idempotent: CREATE ... IF NOT EXISTS. Statements separated by ';' (the
-- refresh_runner splits on ';' and runs each via the Trino HTTP statement API).
--
CREATE SCHEMA IF NOT EXISTS lakehouse.rva_gold_serving;

-- ── Heatmap ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lakehouse.rva_gold_serving.gold_serving_heatmap_tile_5min (
    store_id        VARCHAR,
    camera_id       VARCHAR,
    bucket_start    TIMESTAMP(6),
    bucket_end      TIMESTAMP(6),
    metric_date     DATE,
    grid_width      INTEGER,
    grid_height     INTEGER,
    tile_x          INTEGER,
    tile_y          INTEGER,
    detection_count BIGINT,
    avg_conf        DOUBLE,
    source_rows     BIGINT,
    refreshed_at    TIMESTAMP(6)
) WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['metric_date', 'bucket(camera_id, 16)']);

CREATE TABLE IF NOT EXISTS lakehouse.rva_gold_serving.gold_serving_heatmap_tile_hour (
    store_id        VARCHAR,
    camera_id       VARCHAR,
    bucket_hour     TIMESTAMP(6),
    metric_date     DATE,
    grid_width      INTEGER,
    grid_height     INTEGER,
    tile_x          INTEGER,
    tile_y          INTEGER,
    detection_count BIGINT,
    avg_conf        DOUBLE,
    refreshed_at    TIMESTAMP(6)
) WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['metric_date', 'bucket(camera_id, 16)']);

-- ── Traffic ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lakehouse.rva_gold_serving.gold_serving_traffic_hourly (
    store_id         VARCHAR,
    camera_id        VARCHAR,
    bucket_hour      TIMESTAMP(6),
    metric_date      DATE,
    hour_of_day      INTEGER,
    detection_count  BIGINT,
    avg_people_count DOUBLE,
    max_people_count BIGINT,
    avg_conf         DOUBLE,
    refreshed_at     TIMESTAMP(6)
) WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['metric_date', 'bucket(camera_id, 16)']);

CREATE TABLE IF NOT EXISTS lakehouse.rva_gold_serving.gold_serving_traffic_daily (
    store_id             VARCHAR,
    camera_id            VARCHAR,
    metric_date          DATE,
    detection_count      BIGINT,
    avg_people_count     DOUBLE,
    max_people_count     BIGINT,
    avg_conf             DOUBLE,
    peak_hour            INTEGER,
    peak_hour_detections BIGINT,
    refreshed_at         TIMESTAMP(6)
) WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['metric_date', 'bucket(camera_id, 16)']);

-- ── Queue ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lakehouse.rva_gold_serving.gold_serving_queue_hourly (
    store_id           VARCHAR,
    camera_id          VARCHAR,
    queue_zone_id      VARCHAR,
    bucket_hour        TIMESTAMP(6),
    metric_date        DATE,
    sessions           BIGINT,
    avg_wait_sec       DOUBLE,
    p50_wait_sec       DOUBLE,
    p90_wait_sec       DOUBLE,
    max_wait_sec       DOUBLE,
    avg_frame_count    DOUBLE,
    sla_breach_count   BIGINT,
    sla_threshold_sec  INTEGER,
    refreshed_at       TIMESTAMP(6)
) WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['metric_date', 'bucket(camera_id, 16)']);

CREATE TABLE IF NOT EXISTS lakehouse.rva_gold_serving.gold_serving_queue_daily (
    store_id           VARCHAR,
    camera_id          VARCHAR,
    queue_zone_id      VARCHAR,
    metric_date        DATE,
    sessions           BIGINT,
    avg_wait_sec       DOUBLE,
    p50_wait_sec       DOUBLE,
    p90_wait_sec       DOUBLE,
    max_wait_sec       DOUBLE,
    sla_breach_count   BIGINT,
    sla_threshold_sec  INTEGER,
    refreshed_at       TIMESTAMP(6)
) WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['metric_date', 'bucket(camera_id, 16)']);

-- ── Zone (sourced directly from silver_detections_v2) ──────────────────────────────
CREATE TABLE IF NOT EXISTS lakehouse.rva_gold_serving.gold_serving_zone_hourly (
    store_id         VARCHAR,
    camera_id        VARCHAR,
    zone_id          VARCHAR,
    zone_type        VARCHAR,
    bucket_hour      TIMESTAMP(6),
    metric_date      DATE,
    avg_occupancy    DOUBLE,
    max_occupancy    BIGINT,
    detection_count  BIGINT,
    occupied_minutes BIGINT,
    refreshed_at     TIMESTAMP(6)
) WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['metric_date', 'bucket(camera_id, 16)']);

CREATE TABLE IF NOT EXISTS lakehouse.rva_gold_serving.gold_serving_zone_daily (
    store_id         VARCHAR,
    camera_id        VARCHAR,
    zone_id          VARCHAR,
    zone_type        VARCHAR,
    metric_date      DATE,
    avg_occupancy    DOUBLE,
    max_occupancy    BIGINT,
    detection_count  BIGINT,
    occupied_minutes BIGINT,
    refreshed_at     TIMESTAMP(6)
) WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['metric_date', 'bucket(camera_id, 16)']);

-- ── Dwell ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lakehouse.rva_gold_serving.gold_serving_dwell_daily (
    store_id            VARCHAR,
    camera_id           VARCHAR,
    metric_date         DATE,
    track_count         BIGINT,
    avg_dwell_sec       DOUBLE,
    p50_dwell_sec       DOUBLE,
    p90_dwell_sec       DOUBLE,
    max_dwell_sec       DOUBLE,
    short_dwell_tracks  BIGINT,
    medium_dwell_tracks BIGINT,
    long_dwell_tracks   BIGINT,
    refreshed_at        TIMESTAMP(6)
) WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['metric_date', 'bucket(camera_id, 16)']);

-- ── Executive (store/day) ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lakehouse.rva_gold_serving.gold_serving_executive_daily (
    store_id             VARCHAR,
    metric_date          DATE,
    total_detections     BIGINT,
    active_camera_count  BIGINT,
    avg_dwell_sec        DOUBLE,
    p50_dwell_sec        DOUBLE,
    p90_dwell_sec        DOUBLE,
    queue_sessions       BIGINT,
    avg_queue_wait_sec   DOUBLE,
    p90_queue_wait_sec   DOUBLE,
    max_queue_wait_sec   DOUBLE,
    total_alerts         BIGINT,
    high_alerts          BIGINT,
    latest_alert_ts      TIMESTAMP(6),
    peak_hour            INTEGER,
    peak_hour_detections BIGINT,
    source_min_ts        TIMESTAMP(6),
    source_max_ts        TIMESTAMP(6),
    refreshed_at         TIMESTAMP(6)
) WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['metric_date']);

-- ── Alert (incident counts from gold_alerts) ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS lakehouse.rva_gold_serving.gold_serving_alert_hourly (
    store_id        VARCHAR,
    camera_id       VARCHAR,
    alert_type      VARCHAR,
    severity        VARCHAR,
    bucket_hour     TIMESTAMP(6),
    metric_date     DATE,
    alert_count     BIGINT,
    clip_count      BIGINT,
    latest_alert_ts TIMESTAMP(6),
    refreshed_at    TIMESTAMP(6)
) WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['metric_date', 'bucket(camera_id, 16)']);

CREATE TABLE IF NOT EXISTS lakehouse.rva_gold_serving.gold_serving_alert_daily (
    store_id        VARCHAR,
    camera_id       VARCHAR,
    alert_type      VARCHAR,
    severity        VARCHAR,
    metric_date     DATE,
    alert_count     BIGINT,
    clip_count      BIGINT,
    latest_alert_ts TIMESTAMP(6),
    refreshed_at    TIMESTAMP(6)
) WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['metric_date', 'bucket(camera_id, 16)']);

-- ── Audit / observability ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lakehouse.rva_gold_serving.gold_serving_refresh_audit (
    job_name             VARCHAR,
    run_id               VARCHAR,
    run_mode             VARCHAR,
    gold_serving_table   VARCHAR,
    partition_date       DATE,
    refresh_window_start TIMESTAMP(6),
    refresh_window_end   TIMESTAMP(6),
    source_table         VARCHAR,
    source_row_count     BIGINT,
    output_row_count     BIGINT,
    status               VARCHAR,
    error_message        VARCHAR,
    started_at           TIMESTAMP(6),
    finished_at          TIMESTAMP(6),
    refreshed_at         TIMESTAMP(6)
) WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['partition_date']);

CREATE TABLE IF NOT EXISTS lakehouse.rva_gold_serving.gold_serving_data_quality_results (
    job_name       VARCHAR,
    run_id         VARCHAR,
    check_name     VARCHAR,
    table_name     VARCHAR,
    partition_date DATE,
    severity       VARCHAR,
    status         VARCHAR,
    observed_value VARCHAR,
    expected_rule  VARCHAR,
    checked_at     TIMESTAMP(6)
) WITH (format = 'PARQUET', format_version = 2, partitioning = ARRAY['partition_date']);
