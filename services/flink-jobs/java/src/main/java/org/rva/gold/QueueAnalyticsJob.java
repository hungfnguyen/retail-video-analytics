package org.rva.gold;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.StatementSet;
import org.apache.flink.table.api.TableEnvironment;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * QueueAnalyticsJob builds the first queue and semantic-zone Gold tables from
 * silver_detections_v2. The source table already contains Supervision runtime
 * facts: global_track_id, bottom-center zone assignment, and queue flags.
 */
public class QueueAnalyticsJob {

    public static void main(String[] args) throws Exception {
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

        String createQueueSessions = String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva.gold_queue_sessions (",
                "  store_id             STRING,",
                "  camera_id            STRING,",
                "  queue_zone_id        STRING,",
                "  global_track_id      STRING,",
                "  visit_date           DATE,",
                "  enter_ts             TIMESTAMP_LTZ(3),",
                "  exit_ts              TIMESTAMP_LTZ(3),",
                "  wait_time_sec        BIGINT,",
                "  frame_count          BIGINT,",
                "  completed            BOOLEAN,",
                "  last_track_id        BIGINT,",
                "  raw_track_id_count   BIGINT,",
                "  PRIMARY KEY (store_id, camera_id, queue_zone_id, global_track_id) NOT ENFORCED",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'store_id,bucket(16, camera_id),days(visit_date)',",
                "  'write.upsert.enabled' = 'true'",
                ")"
        );
        tEnv.executeSql(createQueueSessions);

        String createZoneMinuteMetrics = String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva.gold_zone_minute_metrics (",
                "  store_id             STRING,",
                "  camera_id            STRING,",
                "  zone_id              STRING,",
                "  zone_type            STRING,",
                "  window_start         TIMESTAMP_LTZ(3),",
                "  window_end           TIMESTAMP_LTZ(3),",
                "  avg_occupancy        DOUBLE,",
                "  max_occupancy        BIGINT,",
                "  unique_visitors      BIGINT,",
                "  detection_count      BIGINT,",
                "  PRIMARY KEY (store_id, camera_id, zone_id, window_start) NOT ENFORCED",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'store_id,bucket(16, camera_id),days(window_start)',",
                "  'write.upsert.enabled' = 'true'",
                ")"
        );
        tEnv.executeSql(createZoneMinuteMetrics);

        String insertQueueSessions = String.join("\n",
                "INSERT INTO rva.gold_queue_sessions",
                "SELECT",
                "  store_id,",
                "  camera_id,",
                "  queue_zone_id,",
                "  global_track_id,",
                "  CAST(MIN(capture_ts) AS DATE) AS visit_date,",
                "  MIN(capture_ts) AS enter_ts,",
                "  MAX(capture_ts) AS exit_ts,",
                "  TIMESTAMPDIFF(SECOND, MIN(capture_ts), MAX(capture_ts)) AS wait_time_sec,",
                "  COUNT(DISTINCT frame_index) AS frame_count,",
                "  FALSE AS completed,",
                "  MAX(track_id) AS last_track_id,",
                "  COUNT(DISTINCT raw_track_id) AS raw_track_id_count",
                "FROM rva.silver_detections_v2 /*+ OPTIONS('streaming'='true', 'monitor-interval'='1s', 'starting-strategy'='TABLE_SCAN_THEN_INCREMENTAL') */",
                "WHERE in_queue = TRUE",
                "  AND queue_zone_id IS NOT NULL",
                "  AND global_track_id IS NOT NULL",
                "  AND capture_ts IS NOT NULL",
                "GROUP BY store_id, camera_id, queue_zone_id, global_track_id"
        );

        String insertZoneMinuteMetrics = String.join("\n",
                "INSERT INTO rva.gold_zone_minute_metrics",
                "WITH windowed AS (",
                "  SELECT",
                "    store_id, camera_id, primary_zone_id, primary_zone_type, frame_index, global_track_id,",
                "    TO_TIMESTAMP_LTZ(UNIX_TIMESTAMP(DATE_FORMAT(capture_ts, 'yyyy-MM-dd HH:mm:00')) * 1000, 3) AS window_start",
                "  FROM rva.silver_detections_v2 /*+ OPTIONS('streaming'='true', 'monitor-interval'='1s', 'starting-strategy'='TABLE_SCAN_THEN_INCREMENTAL') */",
                "  WHERE primary_zone_id IS NOT NULL",
                "    AND global_track_id IS NOT NULL",
                "    AND capture_ts IS NOT NULL",
                "),",
                "frame_counts AS (",
                "  SELECT",
                "    store_id, camera_id, primary_zone_id, primary_zone_type, window_start, frame_index,",
                "    COUNT(*) AS frame_occupancy",
                "  FROM windowed",
                "  GROUP BY store_id, camera_id, primary_zone_id, primary_zone_type, window_start, frame_index",
                "),",
                "visitor_counts AS (",
                "  SELECT",
                "    store_id, camera_id, primary_zone_id, primary_zone_type, window_start,",
                "    COUNT(DISTINCT global_track_id) AS unique_visitors,",
                "    COUNT(*) AS detection_count",
                "  FROM windowed",
                "  GROUP BY store_id, camera_id, primary_zone_id, primary_zone_type, window_start",
                ")",
                "SELECT",
                "  f.store_id,",
                "  f.camera_id,",
                "  f.primary_zone_id AS zone_id,",
                "  COALESCE(f.primary_zone_type, 'unknown') AS zone_type,",
                "  f.window_start,",
                "  f.window_start + INTERVAL '1' MINUTE AS window_end,",
                "  AVG(CAST(f.frame_occupancy AS DOUBLE)) AS avg_occupancy,",
                "  MAX(f.frame_occupancy) AS max_occupancy,",
                "  MAX(v.unique_visitors) AS unique_visitors,",
                "  MAX(v.detection_count) AS detection_count",
                "FROM frame_counts f",
                "JOIN visitor_counts v",
                "  ON f.store_id = v.store_id",
                " AND f.camera_id = v.camera_id",
                " AND f.primary_zone_id = v.primary_zone_id",
                " AND f.window_start = v.window_start",
                "GROUP BY f.store_id, f.camera_id, f.primary_zone_id, f.primary_zone_type, f.window_start"
        );

        StatementSet statements = tEnv.createStatementSet();
        statements.addInsertSql(insertQueueSessions);
        statements.addInsertSql(insertZoneMinuteMetrics);
        statements.execute();
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
