-- LEGACY Trino fallback only. Scheduled Gold serving refresh uses Flink batch via submit_batch_job.py.
-- gold_serving_queue_hourly  <- gold_queue_sessions
DELETE FROM lakehouse.rva_gold_serving.gold_serving_queue_hourly
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}';

INSERT INTO lakehouse.rva_gold_serving.gold_serving_queue_hourly
SELECT
    store_id,
    camera_id,
    queue_zone_id,
    CAST(date_trunc('hour', enter_ts) AS timestamp(6)) AS bucket_hour,
    CAST(enter_ts AS DATE) AS metric_date,
    COUNT(*) AS sessions,
    AVG(CAST(wait_time_sec AS DOUBLE)) AS avg_wait_sec,
    CAST(approx_percentile(wait_time_sec, 0.5) AS DOUBLE) AS p50_wait_sec,
    CAST(approx_percentile(wait_time_sec, 0.9) AS DOUBLE) AS p90_wait_sec,
    CAST(MAX(wait_time_sec) AS DOUBLE) AS max_wait_sec,
    AVG(CAST(frame_count AS DOUBLE)) AS avg_frame_count,
    COUNT(*) FILTER (WHERE wait_time_sec >= 120) AS sla_breach_count,
    120 AS sla_threshold_sec,
    CAST(current_timestamp AS timestamp(6)) AS refreshed_at
FROM lakehouse.rva.gold_queue_sessions
WHERE wait_time_sec >= 0
  AND enter_ts IS NOT NULL
  AND queue_zone_id IS NOT NULL
  AND CAST(enter_ts AS DATE) BETWEEN DATE '{start}' AND DATE '{end}'
GROUP BY store_id, camera_id, queue_zone_id, date_trunc('hour', enter_ts), CAST(enter_ts AS DATE);
