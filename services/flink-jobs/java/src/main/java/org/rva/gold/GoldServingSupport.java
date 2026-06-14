package org.rva.gold;

import org.apache.flink.table.api.TableEnvironment;
import org.apache.flink.table.api.TableResult;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

final class GoldServingSupport {

    private GoldServingSupport() {
    }

    static TableEnvironment createBatchEnvironment() {
        var settings = org.apache.flink.table.api.EnvironmentSettings.newInstance()
                .inBatchMode()
                .build();
        TableEnvironment tEnv = TableEnvironment.create(settings);

        Map<String, String> cfg = new LinkedHashMap<>();
        cfg.put("type", "iceberg");
        cfg.put("catalog-impl", "org.apache.iceberg.rest.RESTCatalog");
        cfg.put("uri", getenv("ICEBERG_REST_URI", "http://iceberg-rest:8181"));
        cfg.put("warehouse", ensureWarehouseSuffix(getenv("ICEBERG_WAREHOUSE", "s3://warehouse"), "/iceberg"));
        cfg.put("io-impl", "org.apache.iceberg.aws.s3.S3FileIO");
        cfg.put("s3.endpoint", getenv("S3_ENDPOINT", "https://s3.ap-southeast-2.amazonaws.com"));
        cfg.put("s3.path-style-access", getenv("S3_PATH_STYLE", "false"));
        cfg.put("s3.region", getenv("S3_REGION", "ap-southeast-2"));

        String accessKey = firstNotBlank(System.getenv("S3_ACCESS_KEY"), System.getenv("AWS_ACCESS_KEY_ID"));
        String secretKey = firstNotBlank(System.getenv("S3_SECRET_KEY"), System.getenv("AWS_SECRET_ACCESS_KEY"));
        if (accessKey != null) {
            cfg.put("s3.access-key-id", accessKey);
        }
        if (secretKey != null) {
            cfg.put("s3.secret-access-key", secretKey);
        }

        String catalogSql = "CREATE CATALOG lakehouse WITH (" +
                cfg.entrySet().stream()
                        .map(e -> "'" + e.getKey() + "' = '" + e.getValue() + "'")
                        .collect(Collectors.joining(", ")) +
                ")";
        tEnv.executeSql(catalogSql);
        tEnv.executeSql("USE CATALOG lakehouse");
        tEnv.executeSql("CREATE DATABASE IF NOT EXISTS rva");
        tEnv.executeSql("CREATE DATABASE IF NOT EXISTS rva_gold_serving");
        return tEnv;
    }

    static void ensureServingTables(TableEnvironment tEnv) {
        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_heatmap_tile_5min (",
                "  store_id STRING,",
                "  camera_id STRING,",
                "  bucket_start TIMESTAMP(6),",
                "  bucket_end TIMESTAMP(6),",
                "  metric_date DATE,",
                "  grid_width INT,",
                "  grid_height INT,",
                "  tile_x INT,",
                "  tile_y INT,",
                "  detection_count BIGINT,",
                "  avg_conf DOUBLE,",
                "  source_rows BIGINT,",
                "  refreshed_at TIMESTAMP(6)",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'metric_date,bucket(16, camera_id)'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_heatmap_tile_hour (",
                "  store_id STRING,",
                "  camera_id STRING,",
                "  bucket_hour TIMESTAMP(6),",
                "  metric_date DATE,",
                "  grid_width INT,",
                "  grid_height INT,",
                "  tile_x INT,",
                "  tile_y INT,",
                "  detection_count BIGINT,",
                "  avg_conf DOUBLE,",
                "  refreshed_at TIMESTAMP(6)",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'metric_date,bucket(16, camera_id)'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_traffic_hourly (",
                "  store_id STRING,",
                "  camera_id STRING,",
                "  bucket_hour TIMESTAMP(6),",
                "  metric_date DATE,",
                "  hour_of_day INT,",
                "  detection_count BIGINT,",
                "  avg_people_count DOUBLE,",
                "  max_people_count BIGINT,",
                "  avg_conf DOUBLE,",
                "  refreshed_at TIMESTAMP(6)",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'metric_date,bucket(16, camera_id)'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_traffic_daily (",
                "  store_id STRING,",
                "  camera_id STRING,",
                "  metric_date DATE,",
                "  detection_count BIGINT,",
                "  avg_people_count DOUBLE,",
                "  max_people_count BIGINT,",
                "  avg_conf DOUBLE,",
                "  peak_hour INT,",
                "  peak_hour_detections BIGINT,",
                "  refreshed_at TIMESTAMP(6)",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'metric_date,bucket(16, camera_id)'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_queue_hourly (",
                "  store_id STRING,",
                "  camera_id STRING,",
                "  queue_zone_id STRING,",
                "  bucket_hour TIMESTAMP(6),",
                "  metric_date DATE,",
                "  sessions BIGINT,",
                "  avg_wait_sec DOUBLE,",
                "  p50_wait_sec DOUBLE,",
                "  p90_wait_sec DOUBLE,",
                "  max_wait_sec DOUBLE,",
                "  avg_frame_count DOUBLE,",
                "  sla_breach_count BIGINT,",
                "  sla_threshold_sec INT,",
                "  refreshed_at TIMESTAMP(6)",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'metric_date,bucket(16, camera_id)'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_queue_daily (",
                "  store_id STRING,",
                "  camera_id STRING,",
                "  queue_zone_id STRING,",
                "  metric_date DATE,",
                "  sessions BIGINT,",
                "  avg_wait_sec DOUBLE,",
                "  p50_wait_sec DOUBLE,",
                "  p90_wait_sec DOUBLE,",
                "  max_wait_sec DOUBLE,",
                "  sla_breach_count BIGINT,",
                "  sla_threshold_sec INT,",
                "  refreshed_at TIMESTAMP(6)",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'metric_date,bucket(16, camera_id)'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_zone_hourly (",
                "  store_id STRING,",
                "  camera_id STRING,",
                "  zone_id STRING,",
                "  zone_type STRING,",
                "  bucket_hour TIMESTAMP(6),",
                "  metric_date DATE,",
                "  avg_occupancy DOUBLE,",
                "  max_occupancy BIGINT,",
                "  detection_count BIGINT,",
                "  occupied_minutes BIGINT,",
                "  refreshed_at TIMESTAMP(6)",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'metric_date,bucket(16, camera_id)'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_zone_daily (",
                "  store_id STRING,",
                "  camera_id STRING,",
                "  zone_id STRING,",
                "  zone_type STRING,",
                "  metric_date DATE,",
                "  avg_occupancy DOUBLE,",
                "  max_occupancy BIGINT,",
                "  detection_count BIGINT,",
                "  occupied_minutes BIGINT,",
                "  refreshed_at TIMESTAMP(6)",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'metric_date,bucket(16, camera_id)'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_dwell_daily (",
                "  store_id STRING,",
                "  camera_id STRING,",
                "  metric_date DATE,",
                "  track_count BIGINT,",
                "  avg_dwell_sec DOUBLE,",
                "  p50_dwell_sec DOUBLE,",
                "  p90_dwell_sec DOUBLE,",
                "  max_dwell_sec DOUBLE,",
                "  short_dwell_tracks BIGINT,",
                "  medium_dwell_tracks BIGINT,",
                "  long_dwell_tracks BIGINT,",
                "  refreshed_at TIMESTAMP(6)",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'metric_date,bucket(16, camera_id)'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_executive_daily (",
                "  store_id STRING,",
                "  metric_date DATE,",
                "  total_detections BIGINT,",
                "  active_camera_count BIGINT,",
                "  avg_dwell_sec DOUBLE,",
                "  p50_dwell_sec DOUBLE,",
                "  p90_dwell_sec DOUBLE,",
                "  queue_sessions BIGINT,",
                "  avg_queue_wait_sec DOUBLE,",
                "  p90_queue_wait_sec DOUBLE,",
                "  max_queue_wait_sec DOUBLE,",
                "  total_alerts BIGINT,",
                "  high_alerts BIGINT,",
                "  latest_alert_ts TIMESTAMP(6),",
                "  peak_hour INT,",
                "  peak_hour_detections BIGINT,",
                "  source_min_ts TIMESTAMP(6),",
                "  source_max_ts TIMESTAMP(6),",
                "  refreshed_at TIMESTAMP(6)",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'metric_date'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_alert_hourly (",
                "  store_id STRING,",
                "  camera_id STRING,",
                "  alert_type STRING,",
                "  severity STRING,",
                "  bucket_hour TIMESTAMP(6),",
                "  metric_date DATE,",
                "  alert_count BIGINT,",
                "  clip_count BIGINT,",
                "  latest_alert_ts TIMESTAMP(6),",
                "  refreshed_at TIMESTAMP(6)",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'metric_date,bucket(16, camera_id)'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_alert_daily (",
                "  store_id STRING,",
                "  camera_id STRING,",
                "  alert_type STRING,",
                "  severity STRING,",
                "  metric_date DATE,",
                "  alert_count BIGINT,",
                "  clip_count BIGINT,",
                "  latest_alert_ts TIMESTAMP(6),",
                "  refreshed_at TIMESTAMP(6)",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'metric_date,bucket(16, camera_id)'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_refresh_audit (",
                "  job_name STRING,",
                "  run_id STRING,",
                "  run_mode STRING,",
                "  gold_serving_table STRING,",
                "  partition_date DATE,",
                "  refresh_window_start TIMESTAMP(6),",
                "  refresh_window_end TIMESTAMP(6),",
                "  source_table STRING,",
                "  source_row_count BIGINT,",
                "  output_row_count BIGINT,",
                "  status STRING,",
                "  error_message STRING,",
                "  started_at TIMESTAMP(6),",
                "  finished_at TIMESTAMP(6),",
                "  refreshed_at TIMESTAMP(6)",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'partition_date'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva_gold_serving.gold_serving_data_quality_results (",
                "  job_name STRING,",
                "  run_id STRING,",
                "  check_name STRING,",
                "  table_name STRING,",
                "  partition_date DATE,",
                "  severity STRING,",
                "  status STRING,",
                "  observed_value STRING,",
                "  expected_rule STRING,",
                "  checked_at TIMESTAMP(6)",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'partition_date'",
                ")"
        ));
    }

    static void executeAndAwait(TableEnvironment tEnv, String sql) throws Exception {
        TableResult result = tEnv.executeSql(sql);
        result.await();
    }

    static long scalarLong(TableEnvironment tEnv, String sql) throws Exception {
        try (var it = tEnv.executeSql(sql).collect()) {
            if (it.hasNext()) {
                var row = it.next();
                Object v = row.getField(0);
                if (v == null) {
                    return 0L;
                }
                if (v instanceof Number) {
                    return ((Number) v).longValue();
                }
                return Long.parseLong(String.valueOf(v));
            }
            return 0L;
        }
    }

    static void writeAudit(
            TableEnvironment tEnv,
            String runId,
            String runMode,
            String tableName,
            String sourceTable,
            String start,
            String end,
            Long outputRowCount,
            String status,
            String errorMessage,
            String startedAt,
            String finishedAt
    ) throws Exception {
        String sql = String.join("\n",
                "INSERT INTO rva_gold_serving.gold_serving_refresh_audit",
                "SELECT",
                "  'gold_serving_batch' AS job_name,",
                "  " + sqlString(runId) + " AS run_id,",
                "  " + sqlString(runMode) + " AS run_mode,",
                "  " + sqlString(tableName) + " AS gold_serving_table,",
                "  DATE " + sqlString(end) + " AS partition_date,",
                "  CAST(TIMESTAMP " + sqlString(startedAt) + " AS TIMESTAMP(6)) AS refresh_window_start,",
                "  CAST(TIMESTAMP " + sqlString(finishedAt) + " AS TIMESTAMP(6)) AS refresh_window_end,",
                "  " + sqlString(sourceTable) + " AS source_table,",
                "  CAST(NULL AS BIGINT) AS source_row_count,",
                "  " + (outputRowCount == null ? "CAST(NULL AS BIGINT)" : outputRowCount.toString()) + " AS output_row_count,",
                "  " + sqlString(status) + " AS status,",
                "  " + sqlString(errorMessage) + " AS error_message,",
                "  CAST(TIMESTAMP " + sqlString(startedAt) + " AS TIMESTAMP(6)) AS started_at,",
                "  CAST(TIMESTAMP " + sqlString(finishedAt) + " AS TIMESTAMP(6)) AS finished_at,",
                "  CAST(CURRENT_TIMESTAMP AS TIMESTAMP(6)) AS refreshed_at"
        );
        executeAndAwait(tEnv, sql);
    }

    static String newRunId() {
        return UUID.randomUUID().toString().replace("-", "").substring(0, 12);
    }

    static String getenv(String k, String def) {
        String v = System.getenv(k);
        return (v == null || v.isEmpty()) ? def : v;
    }

    static String firstNotBlank(String... values) {
        for (String v : values) {
            if (v != null && !v.isBlank()) {
                return v;
            }
        }
        return null;
    }

    private static String ensureWarehouseSuffix(String warehouse, String suffix) {
        if (warehouse == null || warehouse.isEmpty()) {
            return warehouse;
        }
        String normalized = warehouse.endsWith("/") ? warehouse.substring(0, warehouse.length() - 1) : warehouse;
        String normalizedSuffix = suffix.startsWith("/") ? suffix : "/" + suffix;
        if (normalized.endsWith(normalizedSuffix)) {
            return normalized;
        }
        return normalized + normalizedSuffix;
    }

    static String sqlString(String value) {
        if (value == null) {
            return "NULL";
        }
        return "'" + value.replace("'", "''") + "'";
    }
}
