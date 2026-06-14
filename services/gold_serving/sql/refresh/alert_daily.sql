-- LEGACY Trino fallback only. Scheduled Gold serving refresh uses Flink batch via submit_batch_job.py.
-- gold_serving_alert_daily  <- gold_serving_alert_hourly (rollup; all additive)
DELETE FROM lakehouse.rva_gold_serving.gold_serving_alert_daily
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}';

INSERT INTO lakehouse.rva_gold_serving.gold_serving_alert_daily
SELECT
    store_id,
    camera_id,
    alert_type,
    severity,
    metric_date,
    SUM(alert_count) AS alert_count,
    SUM(clip_count) AS clip_count,
    CAST(MAX(latest_alert_ts) AS timestamp(6)) AS latest_alert_ts,
    CAST(current_timestamp AS timestamp(6)) AS refreshed_at
FROM lakehouse.rva_gold_serving.gold_serving_alert_hourly
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}'
GROUP BY store_id, camera_id, alert_type, severity, metric_date;
