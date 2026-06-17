INSERT INTO rva_gold_serving.gold_serving_traffic_daily
SELECT
  store_id,
  camera_id,
  metric_date,
  SUM(detection_count) AS detection_count,
  SUM(avg_people_count * detection_count) / NULLIF(SUM(detection_count), 0) AS avg_people_count,
  MAX(max_people_count) AS max_people_count,
  SUM(avg_conf * detection_count) / NULLIF(SUM(detection_count), 0) AS avg_conf,
  CAST(NULL AS INT) AS peak_hour,
  MAX(detection_count) AS peak_hour_detections,
  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at
FROM rva_gold_serving.gold_serving_traffic_hourly
WHERE metric_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
GROUP BY store_id, camera_id, metric_date
