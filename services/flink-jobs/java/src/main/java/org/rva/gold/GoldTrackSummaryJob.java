package org.rva.gold;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.TableEnvironment;
import org.apache.flink.table.api.StatementSet;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

public class GoldTrackSummaryJob {

    public static void main(String[] args) throws Exception {
        EnvironmentSettings settings = EnvironmentSettings.newInstance()
                .inStreamingMode()
                .build();
        TableEnvironment tEnv = TableEnvironment.create(settings);
        tEnv.getConfig().set("table.exec.state.ttl", "3 d");

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

        String createGoldV2 = String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva.gold_track_summary_v2 (",
                "  store_id             STRING,",
                "  camera_id            STRING,",
                "  pipeline_run_id      STRING,",
                "  global_track_id      STRING,",
                "  visit_date           DATE,",
                "  enter_ts             TIMESTAMP_LTZ(3),",
                "  exit_ts              TIMESTAMP_LTZ(3),",
                "  duration_sec         BIGINT,",
                "  frames               BIGINT,",
                "  raw_track_id_count   BIGINT,",
                "  predicted_frames     BIGINT,",
                "  representative_zone_id   STRING,",
                "  representative_zone_type STRING,",
                "  PRIMARY KEY (store_id, camera_id, pipeline_run_id, global_track_id, visit_date) NOT ENFORCED",
                ") PARTITIONED BY (store_id, visit_date) WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'write.upsert.enabled' = 'true'",
                ")");
        tEnv.executeSql(createGoldV2);

        String insertV2Sql = String.join("\n",
                "INSERT INTO rva.gold_track_summary_v2",
                "SELECT",
                "  store_id,",
                "  camera_id,",
                "  pipeline_run_id,",
                "  global_track_id,",
                "  CAST(MIN(capture_ts) AS DATE) AS visit_date,",
                "  MIN(capture_ts) AS enter_ts,",
                "  MAX(capture_ts) AS exit_ts,",
                "  TIMESTAMPDIFF(SECOND, MIN(capture_ts), MAX(capture_ts)) AS duration_sec,",
                "  COUNT(DISTINCT frame_index) AS frames,",
                "  COUNT(DISTINCT raw_track_id) AS raw_track_id_count,",
                "  SUM(CASE WHEN is_predicted THEN 1 ELSE 0 END) AS predicted_frames,",
                "  MIN(primary_zone_id) AS representative_zone_id,",
                "  MIN(primary_zone_type) AS representative_zone_type",
                "FROM rva.silver_detections_v2 /*+ OPTIONS('streaming'='true', 'monitor-interval'='1s', 'starting-strategy'='TABLE_SCAN_THEN_INCREMENTAL') */",
                "WHERE store_id IS NOT NULL",
                "  AND camera_id IS NOT NULL",
                "  AND pipeline_run_id IS NOT NULL",
                "  AND global_track_id IS NOT NULL",
                "  AND capture_ts IS NOT NULL",
                "GROUP BY store_id, camera_id, pipeline_run_id, global_track_id");

        StatementSet statements = tEnv.createStatementSet();
        statements.addInsertSql(insertV2Sql);
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
