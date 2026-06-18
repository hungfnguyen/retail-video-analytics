INSERT INTO rva_gold_serving.gold_serving_executive_daily
WITH traffic AS (
  SELECT store_id, metric_date,
         SUM(detection_count) AS total_detections,
         COUNT(DISTINCT camera_id) AS active_camera_count
  FROM rva_gold_serving.gold_serving_traffic_daily
  WHERE metric_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
  GROUP BY store_id, metric_date
),
window_ts AS (
  SELECT store_id, metric_date,
         CAST(MIN(bucket_hour) AS TIMESTAMP(6)) AS source_min_ts,
         CAST(MAX(bucket_hour) AS TIMESTAMP(6)) AS source_max_ts
  FROM rva_gold_serving.gold_serving_traffic_hourly
  WHERE metric_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
  GROUP BY store_id, metric_date
),
peak_src AS (
  SELECT store_id, metric_date, hour_of_day, SUM(detection_count) AS d
  FROM rva_gold_serving.gold_serving_traffic_hourly
  WHERE metric_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
  GROUP BY store_id, metric_date, hour_of_day
),
peak AS (
  SELECT store_id, metric_date,
         CAST(NULL AS INT) AS peak_hour,
         MAX(d) AS peak_hour_detections
  FROM peak_src GROUP BY store_id, metric_date
),
dwell AS (
  SELECT store_id, metric_date,
         SUM(avg_dwell_sec * track_count) / NULLIF(SUM(track_count), 0) AS avg_dwell_sec
  FROM rva_gold_serving.gold_serving_dwell_daily
  WHERE metric_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
  GROUP BY store_id, metric_date
),
queue AS (
  SELECT store_id, metric_date,
         SUM(sessions) AS queue_sessions,
         SUM(avg_wait_sec * sessions) / NULLIF(SUM(sessions), 0) AS avg_queue_wait_sec,
         MAX(max_wait_sec) AS max_queue_wait_sec
  FROM rva_gold_serving.gold_serving_queue_daily
  WHERE metric_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
  GROUP BY store_id, metric_date
),
alerts AS (
  SELECT store_id, metric_date,
         SUM(alert_count) AS total_alerts,
         SUM(CASE WHEN severity = 'high' THEN alert_count ELSE CAST(0 AS BIGINT) END) AS high_alerts,
         CAST(MAX(latest_alert_ts) AS TIMESTAMP(6)) AS latest_alert_ts
  FROM rva_gold_serving.gold_serving_alert_daily
  WHERE metric_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
  GROUP BY store_id, metric_date
)
SELECT
  t.store_id,
  t.metric_date,
  t.total_detections,
  t.active_camera_count,
  d.avg_dwell_sec,
  CAST(NULL AS DOUBLE) AS p50_dwell_sec,
  CAST(NULL AS DOUBLE) AS p90_dwell_sec,
  COALESCE(q.queue_sessions, CAST(0 AS BIGINT)) AS queue_sessions,
  q.avg_queue_wait_sec,
  CAST(NULL AS DOUBLE) AS p90_queue_wait_sec,
  q.max_queue_wait_sec,
  COALESCE(a.total_alerts, CAST(0 AS BIGINT)) AS total_alerts,
  COALESCE(a.high_alerts, CAST(0 AS BIGINT)) AS high_alerts,
  a.latest_alert_ts,
  p.peak_hour,
  p.peak_hour_detections,
  w.source_min_ts,
  w.source_max_ts,
  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at
FROM traffic t
LEFT JOIN window_ts w ON t.store_id = w.store_id AND t.metric_date = w.metric_date
LEFT JOIN peak p ON t.store_id = p.store_id AND t.metric_date = p.metric_date
LEFT JOIN dwell d ON t.store_id = d.store_id AND t.metric_date = d.metric_date
LEFT JOIN queue q ON t.store_id = q.store_id AND t.metric_date = q.metric_date
LEFT JOIN alerts a ON t.store_id = a.store_id AND t.metric_date = a.metric_date
