-- LEGACY Trino fallback only. Scheduled Gold serving refresh uses Flink batch via submit_batch_job.py.
-- gold_serving_traffic_hourly  <- silver_detections_v2 (per-frame inner agg, per-hour outer)
DELETE FROM lakehouse.rva_gold_serving.gold_serving_traffic_hourly
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}';

INSERT INTO lakehouse.rva_gold_serving.gold_serving_traffic_hourly
WITH frame_stats AS (
    SELECT
        store_id,
        camera_id,
        bucket_hour,
        metric_date,
        hour_of_day,
        SUM(frame_det) AS detection_count,
        CAST(SUM(frame_det) AS DOUBLE) / NULLIF(COUNT(*), 0) AS avg_people_count,
        MAX(frame_det) AS max_people_count,
        SUM(frame_conf_sum) / NULLIF(SUM(frame_det), 0) AS avg_conf
    FROM (
        SELECT
            store_id,
            camera_id,
            frame_index,
            CAST(date_trunc('hour', capture_ts) AS timestamp(6)) AS bucket_hour,
            CAST(capture_ts AS DATE) AS metric_date,
            CAST(hour(capture_ts) AS INTEGER) AS hour_of_day,
            COUNT(*) AS frame_det,
            SUM(conf) AS frame_conf_sum
        FROM lakehouse.rva.silver_detections_v2
        WHERE class_id = 0
          AND is_predicted = false
          AND capture_ts IS NOT NULL
          AND capture_date BETWEEN DATE '{start}' AND DATE '{end}'
        GROUP BY store_id, camera_id, frame_index, date_trunc('hour', capture_ts),
                 CAST(capture_ts AS DATE), hour(capture_ts)
    ) f
    GROUP BY store_id, camera_id, bucket_hour, metric_date, hour_of_day
),
visitor_stats AS (
    SELECT
        store_id,
        camera_id,
        CAST(date_trunc('hour', capture_ts) AS timestamp(6)) AS bucket_hour,
        CAST(capture_ts AS DATE) AS metric_date,
        CAST(hour(capture_ts) AS INTEGER) AS hour_of_day,
        COUNT(DISTINCT CONCAT(COALESCE(pipeline_run_id, 'unknown'), ':', global_track_id)) AS unique_tracks
    FROM lakehouse.rva.silver_detections_v2
    WHERE class_id = 0
      AND is_predicted = false
      AND capture_ts IS NOT NULL
      AND global_track_id IS NOT NULL
      AND capture_date BETWEEN DATE '{start}' AND DATE '{end}'
    GROUP BY store_id, camera_id, date_trunc('hour', capture_ts),
             CAST(capture_ts AS DATE), hour(capture_ts)
)
SELECT
    f.store_id,
    f.camera_id,
    f.bucket_hour,
    f.metric_date,
    f.hour_of_day,
    f.detection_count,
    f.avg_people_count,
    f.max_people_count,
    f.avg_conf,
    COALESCE(v.unique_tracks, CAST(0 AS BIGINT)) AS unique_tracks,
    CAST(current_timestamp AS timestamp(6)) AS refreshed_at
FROM frame_stats f
LEFT JOIN visitor_stats v
  ON f.store_id = v.store_id
 AND f.camera_id = v.camera_id
 AND f.bucket_hour = v.bucket_hour
 AND f.metric_date = v.metric_date
 AND f.hour_of_day = v.hour_of_day;
