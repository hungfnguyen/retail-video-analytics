INSERT INTO rva_gold_serving.gold_serving_alert_hourly
SELECT
  store_id,
  camera_id,
  alert_type,
  severity,
  TO_TIMESTAMP(DATE_FORMAT(CAST(event_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')) AS bucket_hour,
  CAST(event_ts AS DATE) AS metric_date,
  COUNT(*) AS alert_count,
  COUNT(clip_s3_key) AS clip_count,
  CAST(MAX(event_ts) AS TIMESTAMP(6)) AS latest_alert_ts,
  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at
FROM rva.gold_alerts
WHERE event_ts IS NOT NULL
  AND camera_id IS NOT NULL
  AND event_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
GROUP BY store_id, camera_id, alert_type, severity, TO_TIMESTAMP(DATE_FORMAT(CAST(event_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')), CAST(event_ts AS DATE)
