-- gold_serving_traffic_daily  <- gold_serving_traffic_hourly (rollup) + peak hour
DELETE FROM lakehouse.rva_gold_serving.gold_serving_traffic_daily
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}';

INSERT INTO lakehouse.rva_gold_serving.gold_serving_traffic_daily
SELECT
    h.store_id,
    h.camera_id,
    h.metric_date,
    SUM(h.detection_count) AS detection_count,
    SUM(h.avg_people_count * h.detection_count) / NULLIF(SUM(h.detection_count), 0) AS avg_people_count,
    MAX(h.max_people_count) AS max_people_count,
    SUM(h.avg_conf * h.detection_count) / NULLIF(SUM(h.detection_count), 0) AS avg_conf,
    MAX_BY(h.hour_of_day, h.detection_count) AS peak_hour,
    MAX(h.detection_count) AS peak_hour_detections,
    CAST(current_timestamp AS timestamp(6)) AS refreshed_at
FROM lakehouse.rva_gold_serving.gold_serving_traffic_hourly h
WHERE h.metric_date BETWEEN DATE '{start}' AND DATE '{end}'
GROUP BY h.store_id, h.camera_id, h.metric_date;
