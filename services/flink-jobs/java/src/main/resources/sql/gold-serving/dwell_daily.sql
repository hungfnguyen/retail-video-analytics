INSERT INTO rva_gold_serving.gold_serving_dwell_daily
SELECT
  store_id,
  camera_id,
  visit_date AS metric_date,
  COUNT(*) AS track_count,
  AVG(CAST(duration_sec AS DOUBLE)) AS avg_dwell_sec,
  CAST(NULL AS DOUBLE) AS p50_dwell_sec,
  CAST(NULL AS DOUBLE) AS p90_dwell_sec,
  CAST(MAX(duration_sec) AS DOUBLE) AS max_dwell_sec,
  SUM(CASE WHEN duration_sec < 30 THEN CAST(1 AS BIGINT) ELSE CAST(0 AS BIGINT) END) AS short_dwell_tracks,
  SUM(CASE WHEN duration_sec >= 30 AND duration_sec < 120 THEN CAST(1 AS BIGINT) ELSE CAST(0 AS BIGINT) END) AS medium_dwell_tracks,
  SUM(CASE WHEN duration_sec >= 120 THEN CAST(1 AS BIGINT) ELSE CAST(0 AS BIGINT) END) AS long_dwell_tracks,
  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at
FROM rva.gold_track_summary_v2
WHERE store_id IS NOT NULL
  AND camera_id IS NOT NULL
  AND visit_date IS NOT NULL
  AND duration_sec >= 0
  AND visit_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
GROUP BY store_id, camera_id, visit_date
