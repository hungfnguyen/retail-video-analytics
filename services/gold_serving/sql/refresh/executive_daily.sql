-- LEGACY Trino fallback only. Scheduled Gold serving refresh uses Flink batch via submit_batch_job.py.
-- gold_serving_executive_daily  <- store/day rollup of traffic + dwell/queue/alerts
-- Anchored on the traffic spine; percentiles recomputed from gold base (not merged).
DELETE FROM lakehouse.rva_gold_serving.gold_serving_executive_daily
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}';

INSERT INTO lakehouse.rva_gold_serving.gold_serving_executive_daily
WITH traffic AS (
    SELECT store_id, metric_date,
           SUM(detection_count) AS total_detections,
           COUNT(DISTINCT camera_id) AS active_camera_count
    FROM lakehouse.rva_gold_serving.gold_serving_traffic_daily
    WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}'
    GROUP BY store_id, metric_date
),
window_ts AS (
    SELECT store_id, metric_date,
           CAST(MIN(bucket_hour) AS timestamp(6)) AS source_min_ts,
           CAST(MAX(bucket_hour) AS timestamp(6)) AS source_max_ts
    FROM lakehouse.rva_gold_serving.gold_serving_traffic_hourly
    WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}'
    GROUP BY store_id, metric_date
),
peak_src AS (
    SELECT store_id, metric_date, hour_of_day, SUM(detection_count) AS d
    FROM lakehouse.rva_gold_serving.gold_serving_traffic_hourly
    WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}'
    GROUP BY store_id, metric_date, hour_of_day
),
peak AS (
    SELECT store_id, metric_date,
           MAX_BY(hour_of_day, d) AS peak_hour,
           MAX(d) AS peak_hour_detections
    FROM peak_src GROUP BY store_id, metric_date
),
dwell AS (
    SELECT store_id, CAST(visit_date AS DATE) AS metric_date,
           AVG(CAST(duration_sec AS DOUBLE)) AS avg_dwell_sec,
           CAST(approx_percentile(duration_sec, 0.5) AS DOUBLE) AS p50_dwell_sec,
           CAST(approx_percentile(duration_sec, 0.9) AS DOUBLE) AS p90_dwell_sec
    FROM lakehouse.rva.gold_track_summary_v2
    WHERE duration_sec >= 0 AND visit_date BETWEEN DATE '{start}' AND DATE '{end}'
    GROUP BY store_id, CAST(visit_date AS DATE)
),
queue AS (
    SELECT store_id, CAST(enter_ts AS DATE) AS metric_date,
           COUNT(*) AS queue_sessions,
           AVG(CAST(wait_time_sec AS DOUBLE)) AS avg_queue_wait_sec,
           CAST(approx_percentile(wait_time_sec, 0.9) AS DOUBLE) AS p90_queue_wait_sec,
           CAST(MAX(wait_time_sec) AS DOUBLE) AS max_queue_wait_sec
    FROM lakehouse.rva.gold_queue_sessions
    WHERE wait_time_sec >= 0 AND enter_ts IS NOT NULL
      AND CAST(enter_ts AS DATE) BETWEEN DATE '{start}' AND DATE '{end}'
    GROUP BY store_id, CAST(enter_ts AS DATE)
),
alerts AS (
    SELECT store_id, CAST(event_ts AS DATE) AS metric_date,
           COUNT(*) AS total_alerts,
           COUNT(*) FILTER (WHERE severity = 'high') AS high_alerts,
           CAST(MAX(event_ts) AS timestamp(6)) AS latest_alert_ts
    FROM lakehouse.rva.gold_alerts
    WHERE event_ts IS NOT NULL AND CAST(event_ts AS DATE) BETWEEN DATE '{start}' AND DATE '{end}'
    GROUP BY store_id, CAST(event_ts AS DATE)
)
SELECT
    t.store_id,
    t.metric_date,
    t.total_detections,
    t.active_camera_count,
    d.avg_dwell_sec,
    d.p50_dwell_sec,
    d.p90_dwell_sec,
    COALESCE(q.queue_sessions, 0) AS queue_sessions,
    q.avg_queue_wait_sec,
    q.p90_queue_wait_sec,
    q.max_queue_wait_sec,
    COALESCE(a.total_alerts, 0) AS total_alerts,
    COALESCE(a.high_alerts, 0) AS high_alerts,
    a.latest_alert_ts,
    p.peak_hour,
    p.peak_hour_detections,
    w.source_min_ts,
    w.source_max_ts,
    CAST(current_timestamp AS timestamp(6)) AS refreshed_at
FROM traffic t
LEFT JOIN window_ts w ON t.store_id = w.store_id AND t.metric_date = w.metric_date
LEFT JOIN peak p ON t.store_id = p.store_id AND t.metric_date = p.metric_date
LEFT JOIN dwell d ON t.store_id = d.store_id AND t.metric_date = d.metric_date
LEFT JOIN queue q ON t.store_id = q.store_id AND t.metric_date = q.metric_date
LEFT JOIN alerts a ON t.store_id = a.store_id AND t.metric_date = a.metric_date;
