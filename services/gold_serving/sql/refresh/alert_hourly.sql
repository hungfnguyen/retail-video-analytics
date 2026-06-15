-- LEGACY Trino fallback only. Scheduled Gold serving refresh uses Flink batch via submit_batch_job.py.
-- gold_serving_alert_hourly  <- gold_alerts (clip incidents; deduped by alert_id upstream)
DELETE FROM lakehouse.rva_gold_serving.gold_serving_alert_hourly
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}';

INSERT INTO lakehouse.rva_gold_serving.gold_serving_alert_hourly
SELECT
    store_id,
    camera_id,
    alert_type,
    severity,
    CAST(date_trunc('hour', event_ts) AS timestamp(6)) AS bucket_hour,
    CAST(event_ts AS DATE) AS metric_date,
    COUNT(*) AS alert_count,
    COUNT(clip_s3_key) AS clip_count,
    CAST(MAX(event_ts) AS timestamp(6)) AS latest_alert_ts,
    CAST(current_timestamp AS timestamp(6)) AS refreshed_at
FROM lakehouse.rva.gold_alerts
WHERE event_ts IS NOT NULL
  AND camera_id IS NOT NULL
  AND event_date BETWEEN DATE '{start}' AND DATE '{end}'
GROUP BY store_id, camera_id, alert_type, severity, date_trunc('hour', event_ts), CAST(event_ts AS DATE);
