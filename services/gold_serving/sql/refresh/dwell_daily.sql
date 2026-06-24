-- LEGACY Trino fallback only. Scheduled Gold serving refresh uses Flink batch via submit_batch_job.py.
-- gold_serving_dwell_daily  <- gold_camera_daily_dwell
DELETE FROM lakehouse.rva_gold_serving.gold_serving_dwell_daily
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}';

INSERT INTO lakehouse.rva_gold_serving.gold_serving_dwell_daily
SELECT
    store_id,
    camera_id,
    metric_date,
    SUM(track_count) AS track_count,
    SUM(avg_dwell_sec * track_count) / NULLIF(SUM(track_count), 0) AS avg_dwell_sec,
    CAST(NULL AS DOUBLE) AS p50_dwell_sec,
    CAST(NULL AS DOUBLE) AS p90_dwell_sec,
    CAST(NULL AS DOUBLE) AS max_dwell_sec,
    SUM(short_dwell_tracks) AS short_dwell_tracks,
    SUM(track_count - short_dwell_tracks - long_dwell_tracks) AS medium_dwell_tracks,
    SUM(long_dwell_tracks) AS long_dwell_tracks,
    CAST(current_timestamp AS timestamp(6)) AS refreshed_at
FROM lakehouse.rva.gold_camera_daily_dwell
WHERE store_id IS NOT NULL
  AND camera_id IS NOT NULL
  AND metric_date IS NOT NULL
  AND track_count >= 0
  AND metric_date BETWEEN DATE '{start}' AND DATE '{end}'
GROUP BY store_id, camera_id, metric_date;
