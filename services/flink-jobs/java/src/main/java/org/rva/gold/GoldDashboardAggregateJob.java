package org.rva.gold;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.StatementSet;
import org.apache.flink.table.api.TableEnvironment;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

public class GoldDashboardAggregateJob {

    public static void main(String[] args) {
        EnvironmentSettings settings = EnvironmentSettings.newInstance()
                .inStreamingMode()
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
                        .collect(Collectors.joining(", "))
                +
                ")";
        tEnv.executeSql(catalogSql);
        tEnv.executeSql("USE CATALOG lakehouse");
        tEnv.executeSql("CREATE DATABASE IF NOT EXISTS rva");
        tEnv.executeSql("USE rva");

        tEnv.executeSql(createHourlyMetricsSql());
        tEnv.executeSql(createDailyMetricsSql());
        tEnv.executeSql(createDailyDwellSql());
        tEnv.executeSql(createAlertEventsSql());

        StatementSet statements = tEnv.createStatementSet();
        statements.addInsertSql(insertHourlyMetricsSql());
        statements.addInsertSql(insertDailyMetricsSql());
        statements.addInsertSql(insertDailyDwellSql());
        statements.addInsertSql(insertAlertEventsSql());
        statements.execute();
    }

    private static String createHourlyMetricsSql() {
        return String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva.gold_camera_hourly_metrics (",
                "  store_id       STRING,",
                "  camera_id      STRING,",
                "  metric_date    DATE,",
                "  hour_of_day    INT,",
                "  detections     BIGINT,",
                "  unique_tracks  BIGINT,",
                "  avg_conf       DOUBLE,",
                "  PRIMARY KEY (store_id, camera_id, metric_date, hour_of_day) NOT ENFORCED",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'store_id,bucket(16, camera_id),days(metric_date)',",
                "  'write.upsert.enabled' = 'true'",
                ")");
    }

    private static String createDailyMetricsSql() {
        return String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva.gold_camera_daily_metrics (",
                "  store_id       STRING,",
                "  camera_id      STRING,",
                "  metric_date    DATE,",
                "  detections     BIGINT,",
                "  unique_tracks  BIGINT,",
                "  avg_conf       DOUBLE,",
                "  first_seen_ts  TIMESTAMP(3),",
                "  last_seen_ts   TIMESTAMP(3),",
                "  PRIMARY KEY (store_id, camera_id, metric_date) NOT ENFORCED",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'store_id,bucket(16, camera_id),days(metric_date)',",
                "  'write.upsert.enabled' = 'true'",
                ")");
    }

    private static String createDailyDwellSql() {
        return String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva.gold_camera_daily_dwell (",
                "  store_id            STRING,",
                "  camera_id           STRING,",
                "  metric_date         DATE,",
                "  track_count         BIGINT,",
                "  avg_dwell_sec       DOUBLE,",
                "  total_dwell_sec     BIGINT,",
                "  short_dwell_tracks  BIGINT,",
                "  long_dwell_tracks   BIGINT,",
                "  PRIMARY KEY (store_id, camera_id, metric_date) NOT ENFORCED",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'store_id,bucket(16, camera_id),days(metric_date)',",
                "  'write.upsert.enabled' = 'true'",
                ")");
    }

    private static String createAlertEventsSql() {
        return String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva.gold_alert_events (",
                "  alert_id       STRING,",
                "  store_id       STRING,",
                "  camera_id      STRING,",
                "  alert_type     STRING,",
                "  severity       STRING,",
                "  event_ts       TIMESTAMP(3),",
                "  event_date     DATE,",
                "  trigger_value  INT,",
                "  threshold      INT,",
                "  status         STRING,",
                "  clip_s3_uri    STRING,",
                "  PRIMARY KEY (alert_id) NOT ENFORCED",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'store_id,bucket(16, camera_id),days(event_date)',",
                "  'write.upsert.enabled' = 'true'",
                ")");
    }

    private static String insertHourlyMetricsSql() {
        return String.join("\n",
                "INSERT INTO rva.gold_camera_hourly_metrics",
                "SELECT",
                "  store_id,",
                "  camera_id,",
                "  CAST(capture_ts AS DATE) AS metric_date,",
                "  CAST(HOUR(capture_ts) AS INT) AS hour_of_day,",
                "  COUNT(*) AS detections,",
                "  COUNT(DISTINCT track_id) AS unique_tracks,",
                "  AVG(conf) AS avg_conf",
                "FROM rva.silver_detections /*+ OPTIONS('streaming'='true', 'monitor-interval'='1s', 'starting-strategy'='TABLE_SCAN_THEN_INCREMENTAL') */",
                "WHERE store_id IS NOT NULL",
                "  AND camera_id IS NOT NULL",
                "  AND capture_ts IS NOT NULL",
                "  AND track_id IS NOT NULL",
                "GROUP BY store_id, camera_id, CAST(capture_ts AS DATE), CAST(HOUR(capture_ts) AS INT)");
    }

    private static String insertDailyMetricsSql() {
        return String.join("\n",
                "INSERT INTO rva.gold_camera_daily_metrics",
                "SELECT",
                "  store_id,",
                "  camera_id,",
                "  CAST(capture_ts AS DATE) AS metric_date,",
                "  COUNT(*) AS detections,",
                "  COUNT(DISTINCT track_id) AS unique_tracks,",
                "  AVG(conf) AS avg_conf,",
                "  MIN(capture_ts) AS first_seen_ts,",
                "  MAX(capture_ts) AS last_seen_ts",
                "FROM rva.silver_detections /*+ OPTIONS('streaming'='true', 'monitor-interval'='1s', 'starting-strategy'='TABLE_SCAN_THEN_INCREMENTAL') */",
                "WHERE store_id IS NOT NULL",
                "  AND camera_id IS NOT NULL",
                "  AND capture_ts IS NOT NULL",
                "  AND track_id IS NOT NULL",
                "GROUP BY store_id, camera_id, CAST(capture_ts AS DATE)");
    }

    private static String insertDailyDwellSql() {
        return String.join("\n",
                "INSERT INTO rva.gold_camera_daily_dwell",
                "SELECT",
                "  store_id,",
                "  camera_id,",
                "  visit_date AS metric_date,",
                "  COUNT(*) AS track_count,",
                "  AVG(duration_sec) AS avg_dwell_sec,",
                "  SUM(duration_sec) AS total_dwell_sec,",
                "  SUM(CASE WHEN duration_sec < 30 THEN CAST(1 AS BIGINT) ELSE CAST(0 AS BIGINT) END) AS short_dwell_tracks,",
                "  SUM(CASE WHEN duration_sec >= 120 THEN CAST(1 AS BIGINT) ELSE CAST(0 AS BIGINT) END) AS long_dwell_tracks",
                "FROM rva.gold_track_summary /*+ OPTIONS('streaming'='true', 'monitor-interval'='1s', 'starting-strategy'='TABLE_SCAN_THEN_INCREMENTAL') */",
                "WHERE store_id IS NOT NULL",
                "  AND camera_id IS NOT NULL",
                "  AND visit_date IS NOT NULL",
                "  AND duration_sec >= 0",
                "GROUP BY store_id, camera_id, visit_date");
    }

    private static String insertAlertEventsSql() {
        String threshold = getenv("ALERT_DENSITY_THRESHOLD", "10");
        return String.join("\n",
                "INSERT INTO rva.gold_alert_events",
                "SELECT",
                "  CONCAT(camera_id, '_', CAST(frame_index AS STRING), '_density_high') AS alert_id,",
                "  store_id,",
                "  camera_id,",
                "  'density_high' AS alert_type,",
                "  'high' AS severity,",
                "  capture_ts AS event_ts,",
                "  CAST(capture_ts AS DATE) AS event_date,",
                "  person_count AS trigger_value,",
                "  " + threshold + " AS threshold,",
                "  'new' AS status,",
                "  CAST(NULL AS STRING) AS clip_s3_uri",
                "FROM (",
                "  SELECT",
                "    store_id,",
                "    camera_id,",
                "    frame_index,",
                "    capture_ts,",
                "    CAST(COUNT(*) AS INT) AS person_count",
                "  FROM rva.silver_detections /*+ OPTIONS('streaming'='true', 'monitor-interval'='1s', 'starting-strategy'='TABLE_SCAN_THEN_INCREMENTAL') */",
                "  WHERE store_id IS NOT NULL",
                "    AND camera_id IS NOT NULL",
                "    AND frame_index IS NOT NULL",
                "    AND capture_ts IS NOT NULL",
                "    AND class_id = 0",
                "  GROUP BY store_id, camera_id, frame_index, capture_ts",
                ")",
                "WHERE person_count > " + threshold);
    }

    private static String getenv(String k, String def) {
        String v = System.getenv(k);
        return (v == null || v.isEmpty()) ? def : v;
    }

    private static String firstNotBlank(String... values) {
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
}
