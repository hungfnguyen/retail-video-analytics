-- gold_serving_traffic_hourly  <- silver_detections_v2 (per-frame inner agg, per-hour outer)
DELETE FROM lakehouse.rva_gold_serving.gold_serving_traffic_hourly
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}';

INSERT INTO lakehouse.rva_gold_serving.gold_serving_traffic_hourly
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
    CAST(current_timestamp AS timestamp(6)) AS refreshed_at
FROM (
    SELECT
        store_id,
        camera_id,
        frame_index,
        CAST(date_trunc('hour', capture_ts) AS timestamp(6)) AS bucket_hour,
        CAST(capture_ts AS DATE) AS metric_date,
        CAST(hour(capture_ts) AS INTEGER) AS hour_of_day,
        COUNT(*) AS frame_det,
        SUM(conf) AS frame_conf_sum
    FROM lakehouse.rva.silver_detections_v2
    WHERE class_id = 0
      AND is_predicted = false
      AND capture_ts IS NOT NULL
      AND CAST(capture_ts AS DATE) BETWEEN DATE '{start}' AND DATE '{end}'
    GROUP BY store_id, camera_id, frame_index, date_trunc('hour', capture_ts),
             CAST(capture_ts AS DATE), hour(capture_ts)
) f
GROUP BY store_id, camera_id, bucket_hour, metric_date, hour_of_day;
