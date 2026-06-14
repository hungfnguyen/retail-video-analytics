INSERT INTO rva_gold_serving.gold_serving_zone_hourly
SELECT
  store_id,
  camera_id,
  zone_id,
  zone_type,
  bucket_hour,
  metric_date,
  CAST(SUM(frame_det) AS DOUBLE) / NULLIF(COUNT(*), 0) AS avg_occupancy,
  MAX(frame_det) AS max_occupancy,
  SUM(frame_det) AS detection_count,
  COUNT(DISTINCT minute_bucket) AS occupied_minutes,
  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at
FROM (
  SELECT
    store_id,
    camera_id,
    primary_zone_id AS zone_id,
    COALESCE(primary_zone_type, 'unknown') AS zone_type,
    TO_TIMESTAMP(DATE_FORMAT(CAST(capture_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')) AS bucket_hour,
    CAST(capture_ts AS DATE) AS metric_date,
    TO_TIMESTAMP(DATE_FORMAT(CAST(capture_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:mm:00')) AS minute_bucket,
    frame_index,
    COUNT(*) AS frame_det
  FROM rva.silver_detections_v2
  WHERE class_id = 0
    AND is_predicted = FALSE
    AND primary_zone_id IS NOT NULL
    AND capture_ts IS NOT NULL
    AND CAST(capture_ts AS DATE) BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
  GROUP BY store_id, camera_id, primary_zone_id, COALESCE(primary_zone_type, 'unknown'),
           TO_TIMESTAMP(DATE_FORMAT(CAST(capture_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')), CAST(capture_ts AS DATE), TO_TIMESTAMP(DATE_FORMAT(CAST(capture_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:mm:00')), frame_index
) f
GROUP BY store_id, camera_id, zone_id, zone_type, bucket_hour, metric_date
