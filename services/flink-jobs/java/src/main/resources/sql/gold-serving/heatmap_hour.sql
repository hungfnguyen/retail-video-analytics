INSERT INTO rva_gold_serving.gold_serving_heatmap_tile_hour
SELECT
  store_id,
  camera_id,
  TO_TIMESTAMP(DATE_FORMAT(CAST(bucket_start AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')) AS bucket_hour,
  metric_date,
  32 AS grid_width,
  24 AS grid_height,
  tile_x,
  tile_y,
  SUM(detection_count) AS detection_count,
  SUM(avg_conf * detection_count) / NULLIF(SUM(detection_count), 0) AS avg_conf,
  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at
FROM rva_gold_serving.gold_serving_heatmap_tile_5min
WHERE metric_date BETWEEN DATE {{START_SQL}} AND DATE {{END_SQL}}
GROUP BY store_id, camera_id, TO_TIMESTAMP(DATE_FORMAT(CAST(bucket_start AS TIMESTAMP(3)), 'yyyy-MM-dd HH:00:00')), metric_date, tile_x, tile_y
