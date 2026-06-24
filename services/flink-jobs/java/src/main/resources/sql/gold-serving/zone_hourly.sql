INSERT INTO rva_gold_serving.gold_serving_zone_hourly
WITH frame_stats AS (
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
    COUNT(DISTINCT minute_bucket) AS occupied_minutes
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
),
visitor_stats AS (
  SELECT
    store_id,
    camera_id,
    primary_zone_id AS zone_id,
    COALESCE(primary_zone_type, 'unknown') AS zone_type,
    TO_TIMESTAMP(DATE_FORMAT(CAST(capture_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')) AS bucket_hour,
    CAST(capture_ts AS DATE) AS metric_date,
    COUNT(DISTINCT global_track_id) AS unique_tracks
  FROM rva.silver_detections_v2
  WHERE class_id = 0
    AND is_predicted = FALSE
    AND primary_zone_id IS NOT NULL
    AND capture_ts IS NOT NULL
    AND global_track_id IS NOT NULL
    AND CAST(capture_ts AS DATE) BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
  GROUP BY store_id, camera_id, primary_zone_id, COALESCE(primary_zone_type, 'unknown'),
           TO_TIMESTAMP(DATE_FORMAT(CAST(capture_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')), CAST(capture_ts AS DATE)
)
SELECT
  f.store_id,
  f.camera_id,
  f.zone_id,
  f.zone_type,
  f.bucket_hour,
  f.metric_date,
  f.avg_occupancy,
  f.max_occupancy,
  f.detection_count,
  f.occupied_minutes,
  COALESCE(v.unique_tracks, CAST(0 AS BIGINT)) AS unique_tracks,
  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at
FROM frame_stats f
LEFT JOIN visitor_stats v
  ON f.store_id = v.store_id
 AND f.camera_id = v.camera_id
 AND f.zone_id = v.zone_id
 AND f.zone_type = v.zone_type
 AND f.bucket_hour = v.bucket_hour
 AND f.metric_date = v.metric_date
