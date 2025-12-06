package org.rva.gold;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.TableEnvironment;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

public class GoldTrackSummaryJob {

    public static void main(String[] args) throws Exception {
        EnvironmentSettings settings = EnvironmentSettings.newInstance()
                .inStreamingMode()
                .build();
        TableEnvironment tEnv = TableEnvironment.create(settings);

        Map<String, String> cfg = new LinkedHashMap<>();
        cfg.put("type", "iceberg");
        cfg.put("catalog-impl", "org.apache.iceberg.rest.RESTCatalog");
        cfg.put("uri", getenv("ICEBERG_REST_URI", "http://iceberg-rest:8181"));
        cfg.put("warehouse", getenv("ICEBERG_WAREHOUSE", "s3://warehouse/iceberg"));
        cfg.put("io-impl", "org.apache.iceberg.aws.s3.S3FileIO");
        cfg.put("s3.endpoint", getenv("S3_ENDPOINT", "http://minio:9000"));
        cfg.put("s3.path-style-access", getenv("S3_PATH_STYLE", "true"));
        cfg.put("s3.region", getenv("S3_REGION", "us-east-1"));

        String accessKey = firstNotBlank(System.getenv("MINIO_ROOT_USER"), System.getenv("AWS_ACCESS_KEY_ID"));
        String secretKey = firstNotBlank(System.getenv("MINIO_ROOT_PASSWORD"), System.getenv("AWS_SECRET_ACCESS_KEY"));
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

        String createGold = String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva.gold_track_summary (",
                "  store_id        STRING,",
                "  camera_id       STRING,",
                "  pipeline_run_id STRING,",
                "  track_id        BIGINT,",
                "  visit_date      DATE,",
                "  enter_ts        TIMESTAMP_LTZ(3),",
                "  exit_ts         TIMESTAMP_LTZ(3),",
                "  duration_sec    BIGINT,",
                "  frames          BIGINT,",
                "  PRIMARY KEY (store_id, camera_id, pipeline_run_id, track_id) NOT ENFORCED",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'store_id,bucket(16, camera_id),days(visit_date)',",
                "  'write.upsert.enabled' = 'true'",
                ")");
        tEnv.executeSql(createGold);

        String insertSql = String.join("\n",
                "INSERT INTO rva.gold_track_summary",
                "SELECT",
                "  store_id,",
                "  camera_id,",
                "  pipeline_run_id,",
                "  track_id,",
                "  CAST(MIN(capture_ts) AS DATE) AS visit_date,",
                "  MIN(capture_ts) AS enter_ts,",
                "  MAX(capture_ts) AS exit_ts,",
                "  TIMESTAMPDIFF(SECOND, MIN(capture_ts), MAX(capture_ts)) AS duration_sec,",
                "  COUNT(DISTINCT frame_index) AS frames",
                "FROM rva.silver_detections /*+ OPTIONS('streaming'='true', 'monitor-interval'='1s') */",
                "WHERE store_id IS NOT NULL",
                "  AND camera_id IS NOT NULL",
                "  AND pipeline_run_id IS NOT NULL",
                "  AND track_id IS NOT NULL",
                "  AND capture_ts IS NOT NULL",
                "GROUP BY store_id, camera_id, pipeline_run_id, track_id");

        tEnv.executeSql(insertSql);
    }

    private static String getenv(String k, String def) {
        String v = System.getenv(k);
        return (v == null || v.isEmpty()) ? def : v;
    }

    private static String firstNotBlank(String a, String b) {
        if (a != null && !a.isBlank())
            return a;
        if (b != null && !b.isBlank())
            return b;
        return null;
    }
}
