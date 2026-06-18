INSERT INTO rva_gold_serving.gold_serving_queue_hourly
SELECT
  store_id,
  camera_id,
  queue_zone_id,
  TO_TIMESTAMP(DATE_FORMAT(CAST(enter_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')) AS bucket_hour,
  CAST(enter_ts AS DATE) AS metric_date,
  COUNT(*) AS sessions,
  AVG(CAST(wait_time_sec AS DOUBLE)) AS avg_wait_sec,
  CAST(NULL AS DOUBLE) AS p50_wait_sec,
  CAST(NULL AS DOUBLE) AS p90_wait_sec,
  CAST(MAX(wait_time_sec) AS DOUBLE) AS max_wait_sec,
  AVG(CAST(frame_count AS DOUBLE)) AS avg_frame_count,
  SUM(CASE WHEN wait_time_sec >= 120 THEN CAST(1 AS BIGINT) ELSE CAST(0 AS BIGINT) END) AS sla_breach_count,
  120 AS sla_threshold_sec,
  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at
FROM rva.gold_queue_sessions
WHERE wait_time_sec >= 0
  AND enter_ts IS NOT NULL
  AND queue_zone_id IS NOT NULL
  AND CAST(enter_ts AS DATE) BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
GROUP BY store_id, camera_id, queue_zone_id, TO_TIMESTAMP(DATE_FORMAT(CAST(enter_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')), CAST(enter_ts AS DATE)
