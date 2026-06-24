INSERT INTO rva_gold_serving.gold_serving_traffic_daily
WITH hourly_rollup AS (
  SELECT
    store_id,
    camera_id,
    metric_date,
    SUM(detection_count) AS detection_count,
    SUM(avg_people_count * detection_count) / NULLIF(SUM(detection_count), 0) AS avg_people_count,
    MAX(max_people_count) AS max_people_count,
    SUM(avg_conf * detection_count) / NULLIF(SUM(detection_count), 0) AS avg_conf
  FROM rva_gold_serving.gold_serving_traffic_hourly
  WHERE metric_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
  GROUP BY store_id, camera_id, metric_date
),
daily_visitors AS (
  SELECT
    store_id,
    camera_id,
    CAST(capture_ts AS DATE) AS metric_date,
    COUNT(DISTINCT CONCAT(COALESCE(pipeline_run_id, 'unknown'), ':', global_track_id)) AS unique_tracks
  FROM rva.silver_detections_v2
  WHERE class_id = 0
    AND is_predicted = FALSE
    AND capture_ts IS NOT NULL
    AND global_track_id IS NOT NULL
    AND CAST(capture_ts AS DATE) BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
  GROUP BY store_id, camera_id, CAST(capture_ts AS DATE)
),
peak_hour_ranked AS (
  SELECT
    store_id,
    camera_id,
    metric_date,
    hour_of_day,
    unique_tracks,
    detection_count,
    ROW_NUMBER() OVER (
      PARTITION BY store_id, camera_id, metric_date
      ORDER BY unique_tracks DESC, detection_count DESC, hour_of_day ASC
    ) AS row_num
  FROM rva_gold_serving.gold_serving_traffic_hourly
  WHERE metric_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
)
SELECT
  h.store_id,
  h.camera_id,
  h.metric_date,
  h.detection_count,
  h.avg_people_count,
  h.max_people_count,
  h.avg_conf,
  p.hour_of_day AS peak_hour,
  COALESCE(p.detection_count, CAST(0 AS BIGINT)) AS peak_hour_detections,
  COALESCE(v.unique_tracks, CAST(0 AS BIGINT)) AS unique_tracks,
  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at
FROM hourly_rollup h
LEFT JOIN daily_visitors v
  ON h.store_id = v.store_id
 AND h.camera_id = v.camera_id
 AND h.metric_date = v.metric_date
LEFT JOIN peak_hour_ranked p
  ON h.store_id = p.store_id
 AND h.camera_id = p.camera_id
 AND h.metric_date = p.metric_date
 AND p.row_num = 1
