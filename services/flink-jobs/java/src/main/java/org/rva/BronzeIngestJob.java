package org.rva;

import org.apache.flink.streaming.api.CheckpointingMode;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.table.api.bridge.java.StreamTableEnvironment;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

public class BronzeIngestJob {

    public static void main(String[] args) throws Exception {

        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.enableCheckpointing(60000L, CheckpointingMode.EXACTLY_ONCE);
        env.getCheckpointConfig().setMinPauseBetweenCheckpoints(30000L);

        StreamTableEnvironment tEnv = StreamTableEnvironment.create(env);

        Map<String, String> cfg = new LinkedHashMap<>();
        cfg.put("type", "iceberg");
        cfg.put("catalog-impl", "org.apache.iceberg.rest.RESTCatalog");
        cfg.put("uri", getenv("ICEBERG_REST_URI", "http://iceberg-rest:8181"));
        cfg.put("warehouse", ensureWarehouseSuffix(getenv("ICEBERG_WAREHOUSE", "s3://warehouse"), "/iceberg"));
        cfg.put("io-impl", "org.apache.iceberg.aws.s3.S3FileIO");
        cfg.put("s3.endpoint", getenv("S3_ENDPOINT", "http://minio:9000"));
        cfg.put("s3.path-style-access", getenv("S3_PATH_STYLE", "true"));
        cfg.put("s3.region", getenv("S3_REGION", "us-east-1"));

        String accessKey = firstNotBlank(System.getenv("MINIO_ROOT_USER"), System.getenv("AWS_ACCESS_KEY_ID"), System.getenv("S3_ACCESS_KEY"));
        String secretKey = firstNotBlank(System.getenv("MINIO_ROOT_PASSWORD"), System.getenv("AWS_SECRET_ACCESS_KEY"), System.getenv("S3_SECRET_KEY"));
        if (accessKey != null) {
            cfg.put("s3.access-key-id", accessKey);
        }
        if (secretKey != null) {
            cfg.put("s3.secret-access-key", secretKey);
        }

        String catalogSql = "CREATE CATALOG lakehouse WITH (" + cfg.entrySet().stream()
                .map(e -> "'" + e.getKey() + "' = '" + e.getValue() + "'")
                .collect(Collectors.joining(", ")) + ")";

        tEnv.executeSql(catalogSql);

        tEnv.executeSql("CREATE DATABASE IF NOT EXISTS lakehouse.rva");
        tEnv.useCatalog("lakehouse");
        tEnv.useDatabase("rva");

        tEnv.executeSql(
                "CREATE TABLE IF NOT EXISTS bronze_raw (" +
                        "  schema_version STRING," +
                        "  event_id STRING," +
                        "  pipeline_run_id STRING," +
                        "  frame_index BIGINT," +
                        "  payload STRING," +
                        "  camera_id STRING," +
                        "  store_id STRING," +
                        "  ingest_ts TIMESTAMP(6)" +
                        ") PARTITIONED BY (store_id) " +
                        "WITH ('format-version'='2','write.format.default'='parquet')");

        tEnv.executeSql(
                "CREATE TEMPORARY TABLE pulsar_source (" +
                        "  raw_payload STRING," +
                        "  event_time AS PROCTIME()" +
                        ") WITH (" +
                        "  'connector'='pulsar'," +
                        "  'service-url'='pulsar://pulsar-broker:6650'," +
                        "  'topics'='persistent://retail/metadata/events'," +
                        "  'format'='raw'," +
                        "  'source.subscription-name'='flink-bronze-java-sub'," +
                        "  'source.start.message-id'='earliest'" +
                        ")");

        tEnv.executeSql(
                "INSERT INTO bronze_raw " +
                        "SELECT " +
                        "  JSON_VALUE(raw_payload, '$.schema_version'), " +
                        "  JSON_VALUE(raw_payload, '$.event_id'), " +
                        "  JSON_VALUE(raw_payload, '$.pipeline_run_id'), " +
                        "  CAST(JSON_VALUE(raw_payload, '$.frame_index') AS BIGINT), " +
                        "  raw_payload, " +
                        "  JSON_VALUE(raw_payload, '$.source.camera_id'), " +
                        "  JSON_VALUE(raw_payload, '$.source.store_id'), " +
                        "  CURRENT_TIMESTAMP " +
                "FROM pulsar_source");
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
