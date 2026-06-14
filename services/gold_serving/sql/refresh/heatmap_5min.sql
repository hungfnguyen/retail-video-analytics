-- LEGACY Trino fallback only. Scheduled Gold serving refresh uses Flink batch via submit_batch_job.py.
-- gold_serving_heatmap_tile_5min  <- silver_detections_v2
-- Parity with heatmap_presence_sql: class_id=0, is_predicted=false, anchors not null,
-- tile clamp LEAST/GREATEST on a 32x24 grid.
DELETE FROM lakehouse.rva_gold_serving.gold_serving_heatmap_tile_5min
WHERE metric_date BETWEEN DATE '{start}' AND DATE '{end}';

INSERT INTO lakehouse.rva_gold_serving.gold_serving_heatmap_tile_5min
SELECT
    store_id,
    camera_id,
    bucket_start,
    bucket_start + INTERVAL '5' MINUTE AS bucket_end,
    CAST(bucket_start AS DATE) AS metric_date,
    32 AS grid_width,
    24 AS grid_height,
    tile_x,
    tile_y,
    COUNT(*) AS detection_count,
    AVG(conf) AS avg_conf,
    COUNT(*) AS source_rows,
    CAST(current_timestamp AS timestamp(6)) AS refreshed_at
FROM (
    SELECT
        store_id,
        camera_id,
        conf,
        CAST(from_unixtime(floor(to_unixtime(capture_ts) / 300) * 300) AS timestamp(6)) AS bucket_start,
        LEAST(31, GREATEST(0, CAST(FLOOR(anchor_x_norm * 32) AS INTEGER))) AS tile_x,
        LEAST(23, GREATEST(0, CAST(FLOOR(anchor_y_norm * 24) AS INTEGER))) AS tile_y
    FROM lakehouse.rva.silver_detections_v2
    WHERE class_id = 0
      AND is_predicted = false
      AND anchor_x_norm IS NOT NULL
      AND anchor_y_norm IS NOT NULL
      AND capture_ts IS NOT NULL
      AND CAST(capture_ts AS DATE) BETWEEN DATE '{start}' AND DATE '{end}'
) base
GROUP BY store_id, camera_id, bucket_start, tile_x, tile_y;
