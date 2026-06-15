INSERT INTO rva_gold_serving.gold_serving_heatmap_tile_5min
SELECT
  store_id,
  camera_id,
  bucket_start,
  TIMESTAMPADD(MINUTE, 5, bucket_start) AS bucket_end,
  CAST(bucket_start AS DATE) AS metric_date,
  32 AS grid_width,
  24 AS grid_height,
  tile_x,
  tile_y,
  COUNT(*) AS detection_count,
  AVG(conf) AS avg_conf,
  COUNT(*) AS source_rows,
  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at
FROM (
  SELECT
    store_id,
    camera_id,
    conf,
    TO_TIMESTAMP(DATE_FORMAT(CAST(capture_ts AS TIMESTAMP(3)), 'yyyy-MM-dd HH:') || LPAD(CAST(CAST(FLOOR(EXTRACT(MINUTE FROM capture_ts) / 5) * 5 AS INT) AS STRING), 2, '0') || ':00') AS bucket_start,
    LEAST(31, GREATEST(0, CAST(FLOOR(anchor_x_norm * 32) AS INT))) AS tile_x,
    LEAST(23, GREATEST(0, CAST(FLOOR(anchor_y_norm * 24) AS INT))) AS tile_y
  FROM rva.silver_detections_v2
  WHERE class_id = 0
    AND is_predicted = FALSE
    AND anchor_x_norm IS NOT NULL
    AND anchor_y_norm IS NOT NULL
    AND capture_ts IS NOT NULL
    AND capture_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
) base
GROUP BY store_id, camera_id, bucket_start, tile_x, tile_y
