INSERT INTO rva_gold_serving.gold_serving_alert_daily
SELECT
  store_id,
  camera_id,
  alert_type,
  severity,
  metric_date,
  SUM(alert_count) AS alert_count,
  SUM(clip_count) AS clip_count,
  CAST(MAX(latest_alert_ts) AS TIMESTAMP(6)) AS latest_alert_ts,
  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at
FROM rva_gold_serving.gold_serving_alert_hourly
WHERE metric_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
GROUP BY store_id, camera_id, alert_type, severity, metric_date
