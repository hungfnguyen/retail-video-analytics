package org.rva.gold;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.TableEnvironment;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * GoldAlertsJob consumes clip_created events from the Pulsar media-events
 * topic and writes them into the Iceberg gold_alerts table for long-term
 * alert history (beyond the Redis 24h TTL).
 *
 * Source: persistent://retail/metadata/media-events  (clip_created events)
 * Sink:   lakehouse.rva.gold_alerts (Iceberg, partitioned by event_date)
 */
public class GoldAlertsJob {

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
        if (accessKey != null) cfg.put("s3.access-key-id", accessKey);
        if (secretKey != null) cfg.put("s3.secret-access-key", secretKey);

        String catalogSql = "CREATE CATALOG lakehouse WITH (" +
                cfg.entrySet().stream()
                        .map(e -> "'" + e.getKey() + "' = '" + e.getValue() + "'")
                        .collect(Collectors.joining(", ")) +
                ")";
        tEnv.executeSql(catalogSql);
        tEnv.executeSql("USE CATALOG lakehouse");
        tEnv.executeSql("CREATE DATABASE IF NOT EXISTS rva");
        tEnv.executeSql("USE rva");

        tEnv.executeSql(String.join("\n",
                "CREATE TABLE IF NOT EXISTS rva.gold_alerts (",
                "  alert_id        STRING,",
                "  camera_id       STRING,",
                "  store_id        STRING,",
                "  alert_type      STRING,",
                "  severity        STRING,",
                "  title           STRING,",
                "  description     STRING,",
                "  zone            STRING,",
                "  event_ts        TIMESTAMP_LTZ(3),",
                "  clip_s3_key     STRING,",
                "  clip_s3_uri     STRING,",
                "  clip_duration_sec DOUBLE,",
                "  event_date      DATE,",
                "  PRIMARY KEY (alert_id) NOT ENFORCED",
                ") WITH (",
                "  'format-version' = '2',",
                "  'write.format.default' = 'parquet',",
                "  'partitioning' = 'days(event_ts)',",
                "  'write.upsert.enabled' = 'true'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "CREATE TEMPORARY TABLE media_events_source (",
                "  raw_payload STRING,",
                "  event_time AS PROCTIME()",
                ") WITH (",
                "  'connector' = 'pulsar',",
                "  'service-url' = 'pulsar://pulsar-broker:6650',",
                "  'topics' = 'persistent://retail/metadata/media-events',",
                "  'format' = 'raw',",
                "  'source.subscription-name' = 'flink-gold-alerts-sub',",
                "  'source.start.message-id' = 'earliest'",
                ")"
        ));

        tEnv.executeSql(String.join("\n",
                "INSERT INTO rva.gold_alerts",
                "SELECT",
                "  JSON_VALUE(raw_payload, '$.alert_id')                         AS alert_id,",
                "  JSON_VALUE(raw_payload, '$.source.camera_id')                 AS camera_id,",
                "  JSON_VALUE(raw_payload, '$.source.store_id')                  AS store_id,",
                "  JSON_VALUE(raw_payload, '$.alert_type')                       AS alert_type,",
                "  'high'                                                         AS severity,",
                "  CONCAT('Incident — ', JSON_VALUE(raw_payload, '$.alert_type')) AS title,",
                "  CONCAT('Camera ', JSON_VALUE(raw_payload, '$.source.camera_id'), ' clip recorded') AS description,",
                "  COALESCE(JSON_VALUE(raw_payload, '$.source.store_id'), 'unknown') AS zone,",
                "  CAST(JSON_VALUE(raw_payload, '$.trigger_ts') AS TIMESTAMP_LTZ(3)) AS event_ts,",
                "  JSON_VALUE(raw_payload, '$.clip_s3_key')                      AS clip_s3_key,",
                "  JSON_VALUE(raw_payload, '$.clip_s3_uri')                      AS clip_s3_uri,",
                "  CAST(JSON_VALUE(raw_payload, '$.clip_duration_sec') AS DOUBLE) AS clip_duration_sec,",
                "  CAST(CAST(JSON_VALUE(raw_payload, '$.trigger_ts') AS TIMESTAMP_LTZ(3)) AS DATE) AS event_date",
                "FROM media_events_source",
                "WHERE JSON_VALUE(raw_payload, '$.event_type') = 'clip_created'",
                "  AND JSON_VALUE(raw_payload, '$.alert_id') IS NOT NULL"
        )).await();
    }

    private static String getenv(String key, String defaultValue) {
        String val = System.getenv(key);
        return (val != null && !val.isBlank()) ? val : defaultValue;
    }

    private static String ensureWarehouseSuffix(String warehouse, String suffix) {
        return warehouse.endsWith(suffix) ? warehouse : warehouse + suffix;
    }

    private static String firstNotBlank(String... values) {
        for (String v : values) {
            if (v != null && !v.isBlank()) return v;
        }
        return null;
    }
}
