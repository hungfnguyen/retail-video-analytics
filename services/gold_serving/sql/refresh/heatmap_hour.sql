-- gold_serving_heatmap_tile_hour  <- gold_serving_heatmap_tile_5min (rollup)
-- Additive: SUM(detection_count). avg_conf = weighted.
DELETE FROM lakehouse.rva_gold_serving.gold_serving_heatmap_tile_hour
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}';

INSERT INTO lakehouse.rva_gold_serving.gold_serving_heatmap_tile_hour
SELECT
    store_id,
    camera_id,
    CAST(date_trunc('hour', bucket_start) AS timestamp(6)) AS bucket_hour,
    metric_date,
    32 AS grid_width,
    24 AS grid_height,
    tile_x,
    tile_y,
    SUM(detection_count) AS detection_count,
    SUM(avg_conf * detection_count) / NULLIF(SUM(detection_count), 0) AS avg_conf,
    CAST(current_timestamp AS timestamp(6)) AS refreshed_at
FROM lakehouse.rva_gold_serving.gold_serving_heatmap_tile_5min
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}'
GROUP BY store_id, camera_id, date_trunc('hour', bucket_start), metric_date, tile_x, tile_y;
