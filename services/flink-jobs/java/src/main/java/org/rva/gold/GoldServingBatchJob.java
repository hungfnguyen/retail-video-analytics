package org.rva.gold;

import org.apache.flink.table.api.TableEnvironment;

import java.time.OffsetDateTime;

public class GoldServingBatchJob {

    public static void main(String[] args) throws Exception {
        Args parsed = Args.parse(args);
        TableEnvironment tEnv = GoldServingSupport.createBatchEnvironment();
        GoldServingSupport.ensureServingTables(tEnv);

        if ("all".equals(parsed.domain)) {
            runTraffic(tEnv, parsed);
            runHeatmap(tEnv, parsed);
            runQueue(tEnv, parsed);
            runZone(tEnv, parsed);
            runDwell(tEnv, parsed);
            runAlert(tEnv, parsed);
            runExecutive(tEnv, parsed);
            return;
        }

        switch (parsed.domain) {
            case "traffic":
                runTraffic(tEnv, parsed);
                break;
            case "heatmap":
                runHeatmap(tEnv, parsed);
                break;
            case "queue":
                runQueue(tEnv, parsed);
                break;
            case "zone":
                runZone(tEnv, parsed);
                break;
            case "dwell":
                runDwell(tEnv, parsed);
                break;
            case "alert":
                runAlert(tEnv, parsed);
                break;
            case "executive":
                runExecutive(tEnv, parsed);
                break;
            default:
                throw new IllegalArgumentException("Unsupported domain: " + parsed.domain);
        }
    }

    private static void runTraffic(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(
                tEnv, args, "gold_serving_traffic_hourly", "silver_detections_v2",
                String.join("\n",
                        "INSERT OVERWRITE rva_gold_serving.gold_serving_traffic_hourly",
                        "SELECT",
                        "  store_id,",
                        "  camera_id,",
                        "  bucket_hour,",
                        "  metric_date,",
                        "  hour_of_day,",
                        "  SUM(frame_det) AS detection_count,",
                        "  CAST(SUM(frame_det) AS DOUBLE) / NULLIF(COUNT(*), 0) AS avg_people_count,",
                        "  MAX(frame_det) AS max_people_count,",
                        "  SUM(frame_conf_sum) / NULLIF(SUM(frame_det), 0) AS avg_conf,",
                        "  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at",
                        "FROM (",
                        "  SELECT",
                        "    store_id,",
                        "    camera_id,",
                        "    frame_index,",
                        "    CAST(DATE_TRUNC('HOUR', capture_ts) AS TIMESTAMP(6)) AS bucket_hour,",
                        "    CAST(capture_ts AS DATE) AS metric_date,",
                        "    CAST(EXTRACT(HOUR FROM capture_ts) AS INT) AS hour_of_day,",
                        "    COUNT(*) AS frame_det,",
                        "    SUM(conf) AS frame_conf_sum",
                        "  FROM rva.silver_detections_v2",
                        "  WHERE class_id = 0",
                        "    AND is_predicted = FALSE",
                        "    AND capture_ts IS NOT NULL",
                        "    AND CAST(capture_ts AS DATE) BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "  GROUP BY store_id, camera_id, frame_index, DATE_TRUNC('HOUR', capture_ts), CAST(capture_ts AS DATE), EXTRACT(HOUR FROM capture_ts)",
                        ") f",
                        "GROUP BY store_id, camera_id, bucket_hour, metric_date, hour_of_day"
                )
        );

        executeStep(
                tEnv, args, "gold_serving_traffic_daily", "gold_serving_traffic_hourly",
                String.join("\n",
                        "INSERT OVERWRITE rva_gold_serving.gold_serving_traffic_daily",
                        "SELECT",
                        "  store_id,",
                        "  camera_id,",
                        "  metric_date,",
                        "  SUM(detection_count) AS detection_count,",
                        "  SUM(avg_people_count * detection_count) / NULLIF(SUM(detection_count), 0) AS avg_people_count,",
                        "  MAX(max_people_count) AS max_people_count,",
                        "  SUM(avg_conf * detection_count) / NULLIF(SUM(detection_count), 0) AS avg_conf,",
                        "  CAST(MAX_BY(CAST(hour_of_day AS BIGINT), detection_count) AS INT) AS peak_hour,",
                        "  MAX(detection_count) AS peak_hour_detections,",
                        "  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at",
                        "FROM rva_gold_serving.gold_serving_traffic_hourly",
                        "WHERE metric_date BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "GROUP BY store_id, camera_id, metric_date"
                )
        );
    }

    private static void runHeatmap(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(
                tEnv, args, "gold_serving_heatmap_tile_5min", "silver_detections_v2",
                String.join("\n",
                        "INSERT OVERWRITE rva_gold_serving.gold_serving_heatmap_tile_5min",
                        "SELECT",
                        "  store_id,",
                        "  camera_id,",
                        "  bucket_start,",
                        "  TIMESTAMPADD(MINUTE, 5, bucket_start) AS bucket_end,",
                        "  CAST(bucket_start AS DATE) AS metric_date,",
                        "  32 AS grid_width,",
                        "  24 AS grid_height,",
                        "  tile_x,",
                        "  tile_y,",
                        "  COUNT(*) AS detection_count,",
                        "  AVG(conf) AS avg_conf,",
                        "  COUNT(*) AS source_rows,",
                        "  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at",
                        "FROM (",
                        "  SELECT",
                        "    store_id,",
                        "    camera_id,",
                        "    conf,",
                        "    CAST(TIMESTAMPADD(MINUTE, - MOD(EXTRACT(MINUTE FROM capture_ts), 5), DATE_TRUNC('MINUTE', capture_ts)) AS TIMESTAMP(6)) AS bucket_start,",
                        "    LEAST(31, GREATEST(0, CAST(FLOOR(anchor_x_norm * 32) AS INT))) AS tile_x,",
                        "    LEAST(23, GREATEST(0, CAST(FLOOR(anchor_y_norm * 24) AS INT))) AS tile_y",
                        "  FROM rva.silver_detections_v2",
                        "  WHERE class_id = 0",
                        "    AND is_predicted = FALSE",
                        "    AND anchor_x_norm IS NOT NULL",
                        "    AND anchor_y_norm IS NOT NULL",
                        "    AND capture_ts IS NOT NULL",
                        "    AND CAST(capture_ts AS DATE) BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        ") base",
                        "GROUP BY store_id, camera_id, bucket_start, tile_x, tile_y"
                )
        );

        executeStep(
                tEnv, args, "gold_serving_heatmap_tile_hour", "gold_serving_heatmap_tile_5min",
                String.join("\n",
                        "INSERT OVERWRITE rva_gold_serving.gold_serving_heatmap_tile_hour",
                        "SELECT",
                        "  store_id,",
                        "  camera_id,",
                        "  CAST(DATE_TRUNC('HOUR', bucket_start) AS TIMESTAMP(6)) AS bucket_hour,",
                        "  metric_date,",
                        "  32 AS grid_width,",
                        "  24 AS grid_height,",
                        "  tile_x,",
                        "  tile_y,",
                        "  SUM(detection_count) AS detection_count,",
                        "  SUM(avg_conf * detection_count) / NULLIF(SUM(detection_count), 0) AS avg_conf,",
                        "  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at",
                        "FROM rva_gold_serving.gold_serving_heatmap_tile_5min",
                        "WHERE metric_date BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "GROUP BY store_id, camera_id, DATE_TRUNC('HOUR', bucket_start), metric_date, tile_x, tile_y"
                )
        );
    }

    private static void runQueue(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(
                tEnv, args, "gold_serving_queue_hourly", "gold_queue_sessions",
                String.join("\n",
                        "INSERT OVERWRITE rva_gold_serving.gold_serving_queue_hourly",
                        "SELECT",
                        "  store_id,",
                        "  camera_id,",
                        "  queue_zone_id,",
                        "  CAST(DATE_TRUNC('HOUR', enter_ts) AS TIMESTAMP(6)) AS bucket_hour,",
                        "  CAST(enter_ts AS DATE) AS metric_date,",
                        "  COUNT(*) AS sessions,",
                        "  AVG(CAST(wait_time_sec AS DOUBLE)) AS avg_wait_sec,",
                        "  CAST(PERCENTILE(wait_time_sec, 0.5) AS DOUBLE) AS p50_wait_sec,",
                        "  CAST(PERCENTILE(wait_time_sec, 0.9) AS DOUBLE) AS p90_wait_sec,",
                        "  CAST(MAX(wait_time_sec) AS DOUBLE) AS max_wait_sec,",
                        "  AVG(CAST(frame_count AS DOUBLE)) AS avg_frame_count,",
                        "  SUM(CASE WHEN wait_time_sec >= 120 THEN CAST(1 AS BIGINT) ELSE CAST(0 AS BIGINT) END) AS sla_breach_count,",
                        "  120 AS sla_threshold_sec,",
                        "  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at",
                        "FROM rva.gold_queue_sessions",
                        "WHERE wait_time_sec >= 0",
                        "  AND enter_ts IS NOT NULL",
                        "  AND queue_zone_id IS NOT NULL",
                        "  AND CAST(enter_ts AS DATE) BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "GROUP BY store_id, camera_id, queue_zone_id, DATE_TRUNC('HOUR', enter_ts), CAST(enter_ts AS DATE)"
                )
        );

        executeStep(
                tEnv, args, "gold_serving_queue_daily", "gold_queue_sessions",
                String.join("\n",
                        "INSERT OVERWRITE rva_gold_serving.gold_serving_queue_daily",
                        "SELECT",
                        "  store_id,",
                        "  camera_id,",
                        "  queue_zone_id,",
                        "  CAST(enter_ts AS DATE) AS metric_date,",
                        "  COUNT(*) AS sessions,",
                        "  AVG(CAST(wait_time_sec AS DOUBLE)) AS avg_wait_sec,",
                        "  CAST(PERCENTILE(wait_time_sec, 0.5) AS DOUBLE) AS p50_wait_sec,",
                        "  CAST(PERCENTILE(wait_time_sec, 0.9) AS DOUBLE) AS p90_wait_sec,",
                        "  CAST(MAX(wait_time_sec) AS DOUBLE) AS max_wait_sec,",
                        "  SUM(CASE WHEN wait_time_sec >= 120 THEN CAST(1 AS BIGINT) ELSE CAST(0 AS BIGINT) END) AS sla_breach_count,",
                        "  120 AS sla_threshold_sec,",
                        "  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at",
                        "FROM rva.gold_queue_sessions",
                        "WHERE wait_time_sec >= 0",
                        "  AND enter_ts IS NOT NULL",
                        "  AND queue_zone_id IS NOT NULL",
                        "  AND CAST(enter_ts AS DATE) BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "GROUP BY store_id, camera_id, queue_zone_id, CAST(enter_ts AS DATE)"
                )
        );
    }

    private static void runZone(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(
                tEnv, args, "gold_serving_zone_hourly", "silver_detections_v2",
                String.join("\n",
                        "INSERT OVERWRITE rva_gold_serving.gold_serving_zone_hourly",
                        "SELECT",
                        "  store_id,",
                        "  camera_id,",
                        "  zone_id,",
                        "  zone_type,",
                        "  bucket_hour,",
                        "  metric_date,",
                        "  CAST(SUM(frame_det) AS DOUBLE) / NULLIF(COUNT(*), 0) AS avg_occupancy,",
                        "  MAX(frame_det) AS max_occupancy,",
                        "  SUM(frame_det) AS detection_count,",
                        "  COUNT(DISTINCT minute_bucket) AS occupied_minutes,",
                        "  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at",
                        "FROM (",
                        "  SELECT",
                        "    store_id,",
                        "    camera_id,",
                        "    primary_zone_id AS zone_id,",
                        "    COALESCE(primary_zone_type, 'unknown') AS zone_type,",
                        "    CAST(DATE_TRUNC('HOUR', capture_ts) AS TIMESTAMP(6)) AS bucket_hour,",
                        "    CAST(capture_ts AS DATE) AS metric_date,",
                        "    DATE_TRUNC('MINUTE', capture_ts) AS minute_bucket,",
                        "    frame_index,",
                        "    COUNT(*) AS frame_det",
                        "  FROM rva.silver_detections_v2",
                        "  WHERE class_id = 0",
                        "    AND is_predicted = FALSE",
                        "    AND primary_zone_id IS NOT NULL",
                        "    AND capture_ts IS NOT NULL",
                        "    AND CAST(capture_ts AS DATE) BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "  GROUP BY store_id, camera_id, primary_zone_id, COALESCE(primary_zone_type, 'unknown'),",
                        "           DATE_TRUNC('HOUR', capture_ts), CAST(capture_ts AS DATE), DATE_TRUNC('MINUTE', capture_ts), frame_index",
                        ") f",
                        "GROUP BY store_id, camera_id, zone_id, zone_type, bucket_hour, metric_date"
                )
        );

        executeStep(
                tEnv, args, "gold_serving_zone_daily", "silver_detections_v2",
                String.join("\n",
                        "INSERT OVERWRITE rva_gold_serving.gold_serving_zone_daily",
                        "SELECT",
                        "  store_id,",
                        "  camera_id,",
                        "  zone_id,",
                        "  zone_type,",
                        "  metric_date,",
                        "  CAST(SUM(frame_det) AS DOUBLE) / NULLIF(COUNT(*), 0) AS avg_occupancy,",
                        "  MAX(frame_det) AS max_occupancy,",
                        "  SUM(frame_det) AS detection_count,",
                        "  COUNT(DISTINCT minute_bucket) AS occupied_minutes,",
                        "  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at",
                        "FROM (",
                        "  SELECT",
                        "    store_id,",
                        "    camera_id,",
                        "    primary_zone_id AS zone_id,",
                        "    COALESCE(primary_zone_type, 'unknown') AS zone_type,",
                        "    CAST(capture_ts AS DATE) AS metric_date,",
                        "    DATE_TRUNC('MINUTE', capture_ts) AS minute_bucket,",
                        "    frame_index,",
                        "    COUNT(*) AS frame_det",
                        "  FROM rva.silver_detections_v2",
                        "  WHERE class_id = 0",
                        "    AND is_predicted = FALSE",
                        "    AND primary_zone_id IS NOT NULL",
                        "    AND capture_ts IS NOT NULL",
                        "    AND CAST(capture_ts AS DATE) BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "  GROUP BY store_id, camera_id, primary_zone_id, COALESCE(primary_zone_type, 'unknown'),",
                        "           CAST(capture_ts AS DATE), DATE_TRUNC('MINUTE', capture_ts), frame_index",
                        ") f",
                        "GROUP BY store_id, camera_id, zone_id, zone_type, metric_date"
                )
        );
    }

    private static void runDwell(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(
                tEnv, args, "gold_serving_dwell_daily", "gold_track_summary_v2",
                String.join("\n",
                        "INSERT OVERWRITE rva_gold_serving.gold_serving_dwell_daily",
                        "SELECT",
                        "  store_id,",
                        "  camera_id,",
                        "  visit_date AS metric_date,",
                        "  COUNT(*) AS track_count,",
                        "  AVG(CAST(duration_sec AS DOUBLE)) AS avg_dwell_sec,",
                        "  CAST(PERCENTILE(duration_sec, 0.5) AS DOUBLE) AS p50_dwell_sec,",
                        "  CAST(PERCENTILE(duration_sec, 0.9) AS DOUBLE) AS p90_dwell_sec,",
                        "  CAST(MAX(duration_sec) AS DOUBLE) AS max_dwell_sec,",
                        "  SUM(CASE WHEN duration_sec < 30 THEN CAST(1 AS BIGINT) ELSE CAST(0 AS BIGINT) END) AS short_dwell_tracks,",
                        "  SUM(CASE WHEN duration_sec >= 30 AND duration_sec < 120 THEN CAST(1 AS BIGINT) ELSE CAST(0 AS BIGINT) END) AS medium_dwell_tracks,",
                        "  SUM(CASE WHEN duration_sec >= 120 THEN CAST(1 AS BIGINT) ELSE CAST(0 AS BIGINT) END) AS long_dwell_tracks,",
                        "  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at",
                        "FROM rva.gold_track_summary_v2",
                        "WHERE store_id IS NOT NULL",
                        "  AND camera_id IS NOT NULL",
                        "  AND visit_date IS NOT NULL",
                        "  AND duration_sec >= 0",
                        "  AND visit_date BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "GROUP BY store_id, camera_id, visit_date"
                )
        );
    }

    private static void runAlert(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(
                tEnv, args, "gold_serving_alert_hourly", "gold_alerts",
                String.join("\n",
                        "INSERT OVERWRITE rva_gold_serving.gold_serving_alert_hourly",
                        "SELECT",
                        "  store_id,",
                        "  camera_id,",
                        "  alert_type,",
                        "  severity,",
                        "  CAST(DATE_TRUNC('HOUR', event_ts) AS TIMESTAMP(6)) AS bucket_hour,",
                        "  CAST(event_ts AS DATE) AS metric_date,",
                        "  COUNT(*) AS alert_count,",
                        "  COUNT(clip_s3_key) AS clip_count,",
                        "  CAST(MAX(event_ts) AS TIMESTAMP(6)) AS latest_alert_ts,",
                        "  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at",
                        "FROM rva.gold_alerts",
                        "WHERE event_ts IS NOT NULL",
                        "  AND camera_id IS NOT NULL",
                        "  AND CAST(event_ts AS DATE) BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "GROUP BY store_id, camera_id, alert_type, severity, DATE_TRUNC('HOUR', event_ts), CAST(event_ts AS DATE)"
                )
        );

        executeStep(
                tEnv, args, "gold_serving_alert_daily", "gold_serving_alert_hourly",
                String.join("\n",
                        "INSERT OVERWRITE rva_gold_serving.gold_serving_alert_daily",
                        "SELECT",
                        "  store_id,",
                        "  camera_id,",
                        "  alert_type,",
                        "  severity,",
                        "  metric_date,",
                        "  SUM(alert_count) AS alert_count,",
                        "  SUM(clip_count) AS clip_count,",
                        "  CAST(MAX(latest_alert_ts) AS TIMESTAMP(6)) AS latest_alert_ts,",
                        "  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at",
                        "FROM rva_gold_serving.gold_serving_alert_hourly",
                        "WHERE metric_date BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "GROUP BY store_id, camera_id, alert_type, severity, metric_date"
                )
        );
    }

    private static void runExecutive(TableEnvironment tEnv, Args args) throws Exception {
        executeStep(
                tEnv, args, "gold_serving_executive_daily", "gold_serving_traffic_daily",
                String.join("\n",
                        "INSERT OVERWRITE rva_gold_serving.gold_serving_executive_daily",
                        "WITH traffic AS (",
                        "  SELECT store_id, metric_date,",
                        "         SUM(detection_count) AS total_detections,",
                        "         COUNT(DISTINCT camera_id) AS active_camera_count",
                        "  FROM rva_gold_serving.gold_serving_traffic_daily",
                        "  WHERE metric_date BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "  GROUP BY store_id, metric_date",
                        "),",
                        "window_ts AS (",
                        "  SELECT store_id, metric_date,",
                        "         CAST(MIN(bucket_hour) AS TIMESTAMP(6)) AS source_min_ts,",
                        "         CAST(MAX(bucket_hour) AS TIMESTAMP(6)) AS source_max_ts",
                        "  FROM rva_gold_serving.gold_serving_traffic_hourly",
                        "  WHERE metric_date BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "  GROUP BY store_id, metric_date",
                        "),",
                        "peak_src AS (",
                        "  SELECT store_id, metric_date, hour_of_day, SUM(detection_count) AS d",
                        "  FROM rva_gold_serving.gold_serving_traffic_hourly",
                        "  WHERE metric_date BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "  GROUP BY store_id, metric_date, hour_of_day",
                        "),",
                        "peak AS (",
                        "  SELECT store_id, metric_date,",
                        "         CAST(MAX_BY(CAST(hour_of_day AS BIGINT), d) AS INT) AS peak_hour,",
                        "         MAX(d) AS peak_hour_detections",
                        "  FROM peak_src GROUP BY store_id, metric_date",
                        "),",
                        "dwell AS (",
                        "  SELECT store_id, visit_date AS metric_date,",
                        "         AVG(CAST(duration_sec AS DOUBLE)) AS avg_dwell_sec,",
                        "         CAST(PERCENTILE(duration_sec, 0.5) AS DOUBLE) AS p50_dwell_sec,",
                        "         CAST(PERCENTILE(duration_sec, 0.9) AS DOUBLE) AS p90_dwell_sec",
                        "  FROM rva.gold_track_summary_v2",
                        "  WHERE duration_sec >= 0 AND visit_date BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "  GROUP BY store_id, visit_date",
                        "),",
                        "queue AS (",
                        "  SELECT store_id, CAST(enter_ts AS DATE) AS metric_date,",
                        "         COUNT(*) AS queue_sessions,",
                        "         AVG(CAST(wait_time_sec AS DOUBLE)) AS avg_queue_wait_sec,",
                        "         CAST(PERCENTILE(wait_time_sec, 0.9) AS DOUBLE) AS p90_queue_wait_sec,",
                        "         CAST(MAX(wait_time_sec) AS DOUBLE) AS max_queue_wait_sec",
                        "  FROM rva.gold_queue_sessions",
                        "  WHERE wait_time_sec >= 0 AND enter_ts IS NOT NULL",
                        "    AND CAST(enter_ts AS DATE) BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "  GROUP BY store_id, CAST(enter_ts AS DATE)",
                        "),",
                        "alerts AS (",
                        "  SELECT store_id, CAST(event_ts AS DATE) AS metric_date,",
                        "         COUNT(*) AS total_alerts,",
                        "         SUM(CASE WHEN severity = 'high' THEN CAST(1 AS BIGINT) ELSE CAST(0 AS BIGINT) END) AS high_alerts,",
                        "         CAST(MAX(event_ts) AS TIMESTAMP(6)) AS latest_alert_ts",
                        "  FROM rva.gold_alerts",
                        "  WHERE event_ts IS NOT NULL AND CAST(event_ts AS DATE) BETWEEN DATE " + GoldServingSupport.sqlString(args.start) + " AND DATE " + GoldServingSupport.sqlString(args.end),
                        "  GROUP BY store_id, CAST(event_ts AS DATE)",
                        ")",
                        "SELECT",
                        "  t.store_id,",
                        "  t.metric_date,",
                        "  t.total_detections,",
                        "  t.active_camera_count,",
                        "  d.avg_dwell_sec,",
                        "  d.p50_dwell_sec,",
                        "  d.p90_dwell_sec,",
                        "  COALESCE(q.queue_sessions, CAST(0 AS BIGINT)) AS queue_sessions,",
                        "  q.avg_queue_wait_sec,",
                        "  q.p90_queue_wait_sec,",
                        "  q.max_queue_wait_sec,",
                        "  COALESCE(a.total_alerts, CAST(0 AS BIGINT)) AS total_alerts,",
                        "  COALESCE(a.high_alerts, CAST(0 AS BIGINT)) AS high_alerts,",
                        "  a.latest_alert_ts,",
                        "  p.peak_hour,",
                        "  p.peak_hour_detections,",
                        "  w.source_min_ts,",
                        "  w.source_max_ts,",
                        "  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at",
                        "FROM traffic t",
                        "LEFT JOIN window_ts w ON t.store_id = w.store_id AND t.metric_date = w.metric_date",
                        "LEFT JOIN peak p ON t.store_id = p.store_id AND t.metric_date = p.metric_date",
                        "LEFT JOIN dwell d ON t.store_id = d.store_id AND t.metric_date = d.metric_date",
                        "LEFT JOIN queue q ON t.store_id = q.store_id AND t.metric_date = q.metric_date",
                        "LEFT JOIN alerts a ON t.store_id = a.store_id AND t.metric_date = a.metric_date"
                )
        );
    }

    private static void executeStep(TableEnvironment tEnv, Args args, String tableName, String sourceTable, String sql) throws Exception {
        String started = OffsetDateTime.now().toLocalDateTime().toString().replace('T', ' ');
        try {
            GoldServingSupport.executeAndAwait(tEnv, sql);
            long out = GoldServingSupport.scalarLong(
                    tEnv,
                    "SELECT COUNT(*) FROM rva_gold_serving." + tableName +
                            " WHERE metric_date BETWEEN DATE " + GoldServingSupport.sqlString(args.start) +
                            " AND DATE " + GoldServingSupport.sqlString(args.end)
            );
            String finished = OffsetDateTime.now().toLocalDateTime().toString().replace('T', ' ');
            GoldServingSupport.writeAudit(tEnv, args.runId, args.runMode, tableName, sourceTable, args.start, args.end, out, "ok", null, started, finished);
        } catch (Exception exc) {
            String finished = OffsetDateTime.now().toLocalDateTime().toString().replace('T', ' ');
            try {
                GoldServingSupport.writeAudit(tEnv, args.runId, args.runMode, tableName, sourceTable, args.start, args.end, null, "error", exc.getMessage(), started, finished);
            } catch (Exception ignored) {
            }
            throw exc;
        }
    }

    private static final class Args {
        final String domain;
        final String start;
        final String end;
        final String runMode;
        final String runId;

        private Args(String domain, String start, String end, String runMode, String runId) {
            this.domain = domain;
            this.start = start;
            this.end = end;
            this.runMode = runMode;
            this.runId = runId;
        }

        static Args parse(String[] args) {
            String domain = null;
            String start = null;
            String end = null;
            String runMode = "airflow";
            for (int i = 0; i < args.length; i++) {
                switch (args[i]) {
                    case "--domain":
                        domain = args[++i];
                        break;
                    case "--start":
                        start = args[++i];
                        break;
                    case "--end":
                        end = args[++i];
                        break;
                    case "--run-mode":
                        runMode = args[++i];
                        break;
                    default:
                        throw new IllegalArgumentException("Unknown arg: " + args[i]);
                }
            }
            if (domain == null || start == null || end == null) {
                throw new IllegalArgumentException("Usage: --domain <traffic|heatmap|queue|zone|dwell|alert|executive|all> --start YYYY-MM-DD --end YYYY-MM-DD [--run-mode mode]");
            }
            return new Args(domain, start, end, runMode, GoldServingSupport.newRunId());
        }
    }
}
