package org.rva;

import org.apache.flink.streaming.api.CheckpointingMode;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.table.api.bridge.java.StreamTableEnvironment;

public class BronzeIngestJob {

    public static void main(String[] args) throws Exception {

        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.enableCheckpointing(60000L, CheckpointingMode.EXACTLY_ONCE);
        env.getCheckpointConfig().setMinPauseBetweenCheckpoints(30000L);

        StreamTableEnvironment tEnv = StreamTableEnvironment.create(env);

        tEnv.executeSql(
                "CREATE CATALOG lakehouse WITH (" +
                        "  'type'='iceberg'," +
                        "  'catalog-impl'='org.apache.iceberg.rest.RESTCatalog'," +
                        "  'uri'='http://iceberg-rest:8181'," +
                        "  'warehouse'='s3://warehouse'," +
                        "  'io-impl'='org.apache.iceberg.aws.s3.S3FileIO'," +
                        "  's3.endpoint'='http://minio:9000'," +
                        "  's3.path-style-access'='true'," +
                        "  's3.access-key-id'='minioadmin'," +
                        "  's3.secret-access-key'='minioadmin123'," +
                        "  'client.region'='us-east-1'," +
                        "  's3.region'='us-east-1'" +
                        ")");

        tEnv.executeSql("CREATE DATABASE IF NOT EXISTS lakehouse.rva");
        tEnv.useCatalog("lakehouse");
        tEnv.useDatabase("rva");

        tEnv.executeSql(
                "CREATE TABLE IF NOT EXISTS bronze_raw (" +
                        "  schema_version STRING," +
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
                        "  JSON_VALUE(raw_payload, '$.pipeline_run_id'), " +
                        "  CAST(JSON_VALUE(raw_payload, '$.frame_index') AS BIGINT), " +
                        "  raw_payload, " +
                        "  JSON_VALUE(raw_payload, '$.source.camera_id'), " +
                        "  JSON_VALUE(raw_payload, '$.source.store_id'), " +
                        "  CURRENT_TIMESTAMP " +
                        "FROM pulsar_source");
    }
}
