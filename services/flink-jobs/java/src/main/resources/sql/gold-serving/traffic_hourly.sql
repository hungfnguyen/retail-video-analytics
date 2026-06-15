INSERT INTO rva_gold_serving.gold_serving_traffic_hourly
SELECT
  store_id,
  camera_id,
  bucket_hour,
  metric_date,
  hour_of_day,
  SUM(frame_det) AS detection_count,
  CAST(SUM(frame_det) AS DOUBLE) / NULLIF(COUNT(*), 0) AS avg_people_count,
  MAX(frame_det) AS max_people_count,
  SUM(frame_conf_sum) / NULLIF(SUM(frame_det), 0) AS avg_conf,
  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at
FROM (
  SELECT
    store_id,
    camera_id,
    frame_index,
    TO_TIMESTAMP(DATE_FORMAT(CAST(capture_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')) AS bucket_hour,
    CAST(capture_ts AS DATE) AS metric_date,
    CAST(EXTRACT(HOUR FROM capture_ts) AS INT) AS hour_of_day,
    COUNT(*) AS frame_det,
    SUM(conf) AS frame_conf_sum
  FROM rva.silver_detections_v2
  WHERE class_id = 0
    AND is_predicted = FALSE
    AND capture_ts IS NOT NULL
    AND capture_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
  GROUP BY store_id, camera_id, frame_index, TO_TIMESTAMP(DATE_FORMAT(CAST(capture_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')), CAST(capture_ts AS DATE), EXTRACT(HOUR FROM capture_ts)
) f
GROUP BY store_id, camera_id, bucket_hour, metric_date, hour_of_day
