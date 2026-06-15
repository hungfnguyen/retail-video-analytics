-- LEGACY Trino fallback only. Scheduled Gold serving refresh uses Flink batch via submit_batch_job.py.
-- gold_serving_zone_hourly  <- silver_detections_v2 (primary_zone_id); per-frame inner agg.
DELETE FROM lakehouse.rva_gold_serving.gold_serving_zone_hourly
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}';

INSERT INTO lakehouse.rva_gold_serving.gold_serving_zone_hourly
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
    COUNT(DISTINCT minute_bucket) AS occupied_minutes,
    CAST(current_timestamp AS timestamp(6)) AS refreshed_at
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
GROUP BY store_id, camera_id, zone_id, zone_type, bucket_hour, metric_date;
