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

        // NOTE: the gold_zone_minute_metrics insert was removed (2026-06-12).
        // It used a stream-stream JOIN of two GROUP BY aggregations feeding an
        // upsert sink; Flink planned that branch as bounded and it finished
        // without ever committing a snapshot (table stayed at 0 rows). The
        // table had no API consumer, so the dead insert was dropped rather than
        // rewritten. See docs/lakehouse/phase1/PHASE1_ZONE_ALERT_DIAGNOSIS_2026-06-12.md.

        StatementSet statements = tEnv.createStatementSet();
        statements.addInsertSql(insertQueueSessions);
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
