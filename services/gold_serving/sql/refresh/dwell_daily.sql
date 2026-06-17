-- LEGACY Trino fallback only. Scheduled Gold serving refresh uses Flink batch via submit_batch_job.py.
-- gold_serving_dwell_daily  <- gold_track_summary_v2
DELETE FROM lakehouse.rva_gold_serving.gold_serving_dwell_daily
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}';

INSERT INTO lakehouse.rva_gold_serving.gold_serving_dwell_daily
SELECT
    store_id,
    camera_id,
    visit_date AS metric_date,
    COUNT(*) AS track_count,
    AVG(CAST(duration_sec AS DOUBLE)) AS avg_dwell_sec,
    CAST(approx_percentile(duration_sec, 0.5) AS DOUBLE) AS p50_dwell_sec,
    CAST(approx_percentile(duration_sec, 0.9) AS DOUBLE) AS p90_dwell_sec,
    CAST(MAX(duration_sec) AS DOUBLE) AS max_dwell_sec,
    COUNT(*) FILTER (WHERE duration_sec < 30) AS short_dwell_tracks,
    COUNT(*) FILTER (WHERE duration_sec >= 30 AND duration_sec < 120) AS medium_dwell_tracks,
    COUNT(*) FILTER (WHERE duration_sec >= 120) AS long_dwell_tracks,
    CAST(current_timestamp AS timestamp(6)) AS refreshed_at
FROM lakehouse.rva.gold_track_summary_v2
WHERE store_id IS NOT NULL
  AND camera_id IS NOT NULL
  AND visit_date IS NOT NULL
  AND duration_sec >= 0
  AND visit_date BETWEEN DATE '{start}' AND DATE '{end}'
GROUP BY store_id, camera_id, visit_date;
