package org.rva.gold;

import org.apache.flink.table.api.TableEnvironment;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
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

    static void configureBatchParallelism(TableEnvironment tEnv, String domain) {
        // By default we respect the cluster's parallelism.default (=1) configured in
        // infrastructure/flink/conf/flink-conf.yaml. On the shared local session
        // cluster the always-on streaming jobs permanently hold most of the network
        // buffer pool, so any batch shuffle with parallelism > 1 fails with
        // "Insufficient number of network buffers". Batch data volume here is tiny,
        // so p=1 is both correct and faster. Operators who run Gold serving on a
        // dedicated/larger batch cluster can still raise parallelism per domain via
        // RVA_GOLD_SERVING_PARALLELISM_<DOMAIN> or RVA_GOLD_SERVING_BATCH_PARALLELISM.
        Integer override = resolveBatchParallelismOverride(domain);
        if (override != null) {
            tEnv.getConfig().set("table.exec.resource.default-parallelism", String.valueOf(override));
        }
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
                ") PARTITIONED BY (metric_date, store_id, camera_id) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet'",
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
                ") PARTITIONED BY (metric_date, store_id, camera_id) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet'",
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
                "  unique_tracks BIGINT,",
                "  refreshed_at TIMESTAMP(6)",
                ") PARTITIONED BY (metric_date, store_id) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet'",
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
                "  unique_tracks BIGINT,",
                "  refreshed_at TIMESTAMP(6)",
                ") PARTITIONED BY (metric_date, store_id) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet'",
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
                ") PARTITIONED BY (metric_date, store_id) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet'",
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
                ") PARTITIONED BY (metric_date, store_id) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet'",
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
                "  unique_tracks BIGINT,",
                "  refreshed_at TIMESTAMP(6)",
                ") PARTITIONED BY (metric_date, store_id) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet'",
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
                "  unique_tracks BIGINT,",
                "  refreshed_at TIMESTAMP(6)",
                ") PARTITIONED BY (metric_date, store_id) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet'",
                ")"
        ));

        ensureColumn(tEnv, "rva_gold_serving.gold_serving_traffic_hourly", "unique_tracks BIGINT");
        ensureColumn(tEnv, "rva_gold_serving.gold_serving_traffic_daily", "unique_tracks BIGINT");
        ensureColumn(tEnv, "rva_gold_serving.gold_serving_zone_hourly", "unique_tracks BIGINT");
        ensureColumn(tEnv, "rva_gold_serving.gold_serving_zone_daily", "unique_tracks BIGINT");

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
                ") PARTITIONED BY (metric_date, store_id) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet'",
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
                ") PARTITIONED BY (metric_date, store_id) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet'",
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
                ") PARTITIONED BY (metric_date, store_id) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet'",
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
                ") PARTITIONED BY (metric_date, store_id) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet'",
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
                ") PARTITIONED BY (partition_date) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet'",
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
                ") PARTITIONED BY (partition_date) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet'",
                ")"
        ));
    }

    private static void ensureColumn(TableEnvironment tEnv, String tableName, String columnDefinition) {
        try {
            tEnv.executeSql("ALTER TABLE " + tableName + " ADD (" + columnDefinition + ")");
        } catch (Exception exc) {
            String message = String.valueOf(exc.getMessage()).toLowerCase();
            if (message.contains("already exists") || message.contains("duplicate")) {
                return;
            }
            throw exc;
        }
    }

    static void executeAndAwait(TableEnvironment tEnv, String sql) throws Exception {
        tEnv.executeSql(sql);
    }

    static String renderSqlResource(String resourcePath, Map<String, String> replacements) {
        try (InputStream input = GoldServingSupport.class.getClassLoader().getResourceAsStream(resourcePath)) {
            if (input == null) {
                throw new IllegalArgumentException("Missing SQL resource: " + resourcePath);
            }
            String sql = new String(input.readAllBytes(), StandardCharsets.UTF_8);
            for (Map.Entry<String, String> entry : replacements.entrySet()) {
                sql = sql.replace(entry.getKey(), entry.getValue());
            }
            return sql;
        } catch (IOException e) {
            throw new RuntimeException("Failed to load SQL resource: " + resourcePath, e);
        }
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

    /**
     * Returns an explicit batch parallelism override for the given domain, or {@code null}
     * to fall back to the cluster's parallelism.default. Only env vars can raise it; there is
     * no hard-coded per-domain elevation because that contradicts the local cluster's
     * network-buffer budget (see {@link #configureBatchParallelism}).
     */
    private static Integer resolveBatchParallelismOverride(String domain) {
        String specificEnv = System.getenv("RVA_GOLD_SERVING_PARALLELISM_" + domain.toUpperCase());
        if (specificEnv != null && !specificEnv.isBlank()) {
            return parsePositiveInt(specificEnv, 1);
        }

        String defaultEnv = System.getenv("RVA_GOLD_SERVING_BATCH_PARALLELISM");
        if (defaultEnv != null && !defaultEnv.isBlank()) {
            return parsePositiveInt(defaultEnv, 1);
        }

        return null;
    }

    private static int parsePositiveInt(String raw, int fallback) {
        try {
            int value = Integer.parseInt(raw.trim());
            return value > 0 ? value : fallback;
        } catch (NumberFormatException ignore) {
            return fallback;
        }
    }
}
