INSERT INTO rva_gold_serving.gold_serving_traffic_hourly
WITH frame_stats AS (
  SELECT
    store_id,
    camera_id,
    bucket_hour,
    metric_date,
    hour_of_day,
    SUM(frame_det) AS detection_count,
    CAST(SUM(frame_det) AS DOUBLE) / NULLIF(COUNT(*), 0) AS avg_people_count,
    MAX(frame_det) AS max_people_count,
    SUM(frame_conf_sum) / NULLIF(SUM(frame_det), 0) AS avg_conf
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
      AND CAST(capture_ts AS DATE) BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
    GROUP BY store_id, camera_id, frame_index, TO_TIMESTAMP(DATE_FORMAT(CAST(capture_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')), CAST(capture_ts AS DATE), EXTRACT(HOUR FROM capture_ts)
  ) f
  GROUP BY store_id, camera_id, bucket_hour, metric_date, hour_of_day
),
visitor_stats AS (
  SELECT
    store_id,
    camera_id,
    TO_TIMESTAMP(DATE_FORMAT(CAST(capture_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')) AS bucket_hour,
    CAST(capture_ts AS DATE) AS metric_date,
    CAST(EXTRACT(HOUR FROM capture_ts) AS INT) AS hour_of_day,
    COUNT(DISTINCT global_track_id) AS unique_tracks
  FROM rva.silver_detections_v2
  WHERE class_id = 0
    AND is_predicted = FALSE
    AND capture_ts IS NOT NULL
    AND global_track_id IS NOT NULL
    AND CAST(capture_ts AS DATE) BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
  GROUP BY store_id, camera_id, TO_TIMESTAMP(DATE_FORMAT(CAST(capture_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')), CAST(capture_ts AS DATE), EXTRACT(HOUR FROM capture_ts)
)
SELECT
  f.store_id,
  f.camera_id,
  f.bucket_hour,
  f.metric_date,
  f.hour_of_day,
  f.detection_count,
  f.avg_people_count,
  f.max_people_count,
  f.avg_conf,
  COALESCE(v.unique_tracks, CAST(0 AS BIGINT)) AS unique_tracks,
  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at
FROM frame_stats f
LEFT JOIN visitor_stats v
  ON f.store_id = v.store_id
 AND f.camera_id = v.camera_id
 AND f.bucket_hour = v.bucket_hour
 AND f.metric_date = v.metric_date
 AND f.hour_of_day = v.hour_of_day
