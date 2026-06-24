-- LEGACY Trino fallback only. Scheduled Gold serving refresh uses Flink batch via submit_batch_job.py.
-- gold_serving_zone_hourly  <- silver_detections_v2 (primary_zone_id); per-frame inner agg.
DELETE FROM lakehouse.rva_gold_serving.gold_serving_zone_hourly
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}';

INSERT INTO lakehouse.rva_gold_serving.gold_serving_zone_hourly
WITH frame_stats AS (
    SELECT
        store_id,
        camera_id,
        zone_id,
        zone_type,
        bucket_hour,
        metric_date,
        CAST(SUM(frame_det) AS DOUBLE) / NULLIF(COUNT(*), 0) AS avg_occupancy,
        MAX(frame_det) AS max_occupancy,
        SUM(frame_det) AS detection_count,
        COUNT(DISTINCT minute_bucket) AS occupied_minutes
    FROM (
        SELECT
            store_id,
            camera_id,
            primary_zone_id AS zone_id,
            COALESCE(primary_zone_type, 'unknown') AS zone_type,
            CAST(date_trunc('hour', capture_ts) AS timestamp(6)) AS bucket_hour,
            CAST(capture_ts AS DATE) AS metric_date,
            date_trunc('minute', capture_ts) AS minute_bucket,
            frame_index,
            COUNT(*) AS frame_det
        FROM lakehouse.rva.silver_detections_v2
        WHERE class_id = 0
          AND is_predicted = false
          AND primary_zone_id IS NOT NULL
          AND capture_ts IS NOT NULL
          AND capture_date BETWEEN DATE '{start}' AND DATE '{end}'
        GROUP BY store_id, camera_id, primary_zone_id, COALESCE(primary_zone_type, 'unknown'),
                 date_trunc('hour', capture_ts), CAST(capture_ts AS DATE),
                 date_trunc('minute', capture_ts), frame_index
    ) f
    GROUP BY store_id, camera_id, zone_id, zone_type, bucket_hour, metric_date
),
visitor_stats AS (
    SELECT
        store_id,
        camera_id,
        primary_zone_id AS zone_id,
        COALESCE(primary_zone_type, 'unknown') AS zone_type,
        CAST(date_trunc('hour', capture_ts) AS timestamp(6)) AS bucket_hour,
        CAST(capture_ts AS DATE) AS metric_date,
        COUNT(DISTINCT CONCAT(COALESCE(pipeline_run_id, 'unknown'), ':', global_track_id)) AS unique_tracks
    FROM lakehouse.rva.silver_detections_v2
    WHERE class_id = 0
      AND is_predicted = false
      AND primary_zone_id IS NOT NULL
      AND capture_ts IS NOT NULL
      AND global_track_id IS NOT NULL
      AND capture_date BETWEEN DATE '{start}' AND DATE '{end}'
    GROUP BY store_id, camera_id, primary_zone_id, COALESCE(primary_zone_type, 'unknown'),
             date_trunc('hour', capture_ts), CAST(capture_ts AS DATE)
)
SELECT
    f.store_id,
    f.camera_id,
    f.zone_id,
    f.zone_type,
    f.bucket_hour,
    f.metric_date,
    f.avg_occupancy,
    f.max_occupancy,
    f.detection_count,
    f.occupied_minutes,
    COALESCE(v.unique_tracks, CAST(0 AS BIGINT)) AS unique_tracks,
    CAST(current_timestamp AS timestamp(6)) AS refreshed_at
FROM frame_stats f
LEFT JOIN visitor_stats v
  ON f.store_id = v.store_id
 AND f.camera_id = v.camera_id
 AND f.zone_id = v.zone_id
 AND f.zone_type = v.zone_type
 AND f.bucket_hour = v.bucket_hour
 AND f.metric_date = v.metric_date;
