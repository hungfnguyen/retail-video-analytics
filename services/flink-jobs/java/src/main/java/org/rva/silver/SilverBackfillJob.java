package org.rva.silver;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.StatementSet;
import org.apache.flink.table.api.TableEnvironment;
import org.rva.silver.udf.ParseDetections;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * One-off bounded Bronze -> Silver historical repair.
 *
 * This job is the only supported path for catch-up / gap repair. The always-on
 * realtime Silver stream must stay focused on fresh data and should never take
 * responsibility for historical replay.
 */
public class SilverBackfillJob {
    public static void main(String[] args) throws Exception {
        EnvironmentSettings settings = EnvironmentSettings.newInstance()
            .inBatchMode()
            .build();
        TableEnvironment tEnv = TableEnvironment.create(settings);
        tEnv.getConfig().set("table.exec.state.ttl", "30 min");
        applyJobParallelism(tEnv, "SILVER_BACKFILL_PARALLELISM", "4");
        tEnv.createTemporarySystemFunction("parse_detections", ParseDetections.class);

        Map<String, String> cfg = new LinkedHashMap<>();
        cfg.put("type", "iceberg");
        cfg.put("catalog-impl", "org.apache.iceberg.rest.RESTCatalog");
        cfg.put("uri", getenv("ICEBERG_REST_URI", "http://iceberg-rest:8181"));
        cfg.put(
            "warehouse",
            ensureWarehouseSuffix(getenv("ICEBERG_WAREHOUSE", "s3://warehouse"), "/iceberg")
        );
        cfg.put("io-impl", "org.apache.iceberg.aws.s3.S3FileIO");
        cfg.put("s3.endpoint", getenv("S3_ENDPOINT", "https://s3.ap-southeast-2.amazonaws.com"));
        cfg.put("s3.path-style-access", getenv("S3_PATH_STYLE", "false"));
        cfg.put("s3.region", getenv("S3_REGION", "ap-southeast-2"));

        String accessKey = firstNotBlank(System.getenv("S3_ACCESS_KEY"), System.getenv("AWS_ACCESS_KEY_ID"));
        String secretKey = firstNotBlank(System.getenv("S3_SECRET_KEY"), System.getenv("AWS_SECRET_ACCESS_KEY"));
        if (accessKey != null) cfg.put("s3.access-key-id", accessKey);
        if (secretKey != null) cfg.put("s3.secret-access-key", secretKey);

        String catalogSql = "CREATE CATALOG lakehouse WITH (" + cfg.entrySet().stream()
            .map(e -> "'" + e.getKey() + "' = '" + e.getValue() + "'")
            .collect(Collectors.joining(", ")) + ")";
        tEnv.executeSql(catalogSql);
        tEnv.executeSql("USE CATALOG lakehouse");
        tEnv.executeSql("CREATE DATABASE IF NOT EXISTS rva");
        tEnv.executeSql("USE rva");

        SilverSchema.ensureTables(tEnv);

        String backfillDateFilter = captureDateFilter(
            System.getenv("SILVER_BACKFILL_START_DATE"),
            System.getenv("SILVER_BACKFILL_END_DATE")
        );

        String insertV2Sql = String.join("\n",
            "INSERT INTO rva.silver_detections_v2",
            "SELECT",
            "  schema_version,",
            "  event_type,",
            "  event_id,",
            "  detection_id,",
            "  pipeline_run_id,",
            "  store_id,",
            "  camera_id,",
            "  frame_index,",
            "  source_frame_index,",
            "  capture_ts,",
            "  img_w,",
            "  img_h,",
            "  det_id,",
            "  class_name,",
            "  class_id,",
            "  conf,",
            "  bbox_x1,",
            "  bbox_y1,",
            "  bbox_x2,",
            "  bbox_y2,",
            "  track_id,",
            "  raw_track_id,",
            "  global_track_id,",
            "  track_state,",
            "  is_predicted,",
            "  anchor_type,",
            "  anchor_x,",
            "  anchor_y,",
            "  anchor_x_norm,",
            "  anchor_y_norm,",
            "  primary_zone_id,",
            "  primary_zone_type,",
            "  in_queue,",
            "  queue_zone_id,",
            "  model_name,",
            "  detector_type,",
            "  tracker_type,",
            "  supervision_version,",
            "  trackers_version,",
            "  zone_config_version,",
            "  processing_ts,",
            "  capture_date",
            "FROM (",
            "  SELECT",
            "    b.schema_version AS schema_version,",
            "    COALESCE(JSON_VALUE(b.payload, '$.event_type'), 'detection_frame') AS event_type,",
            "    COALESCE(b.event_id, JSON_VALUE(b.payload, '$.event_id')) AS event_id,",
            "    CONCAT(COALESCE(b.event_id, JSON_VALUE(b.payload, '$.event_id')), ':', COALESCE(t.det_id, CAST(t.track_id AS STRING))) AS detection_id,",
            "    COALESCE(b.pipeline_run_id, JSON_VALUE(b.payload, '$.pipeline_run_id')) AS pipeline_run_id,",
            "    b.store_id AS store_id,",
            "    b.camera_id AS camera_id,",
            "    CAST(JSON_VALUE(b.payload, '$.frame_index') AS BIGINT) AS frame_index,",
            "    CAST(JSON_VALUE(b.payload, '$.source_frame_index') AS BIGINT) AS source_frame_index,",
            "    TO_TIMESTAMP_LTZ(t.capture_ts_ms, 3) AS capture_ts,",
            "    t.img_w AS img_w,",
            "    t.img_h AS img_h,",
            "    t.det_id AS det_id,",
            "    t.class_name AS class_name,",
            "    t.class_id AS class_id,",
            "    t.conf AS conf,",
            "    t.bbox_x1 AS bbox_x1,",
            "    t.bbox_y1 AS bbox_y1,",
            "    t.bbox_x2 AS bbox_x2,",
            "    t.bbox_y2 AS bbox_y2,",
            "    t.track_id AS track_id,",
            "    t.raw_track_id AS raw_track_id,",
            "    t.global_track_id AS global_track_id,",
            "    t.track_state AS track_state,",
            "    t.is_predicted AS is_predicted,",
            "    t.anchor_type AS anchor_type,",
            "    t.anchor_x AS anchor_x,",
            "    t.anchor_y AS anchor_y,",
            "    t.anchor_x_norm AS anchor_x_norm,",
            "    t.anchor_y_norm AS anchor_y_norm,",
            "    t.primary_zone_id AS primary_zone_id,",
            "    t.primary_zone_type AS primary_zone_type,",
            "    t.in_queue AS in_queue,",
            "    t.queue_zone_id AS queue_zone_id,",
            "    JSON_VALUE(b.payload, '$.runtime.model_name') AS model_name,",
            "    JSON_VALUE(b.payload, '$.runtime.detector_type') AS detector_type,",
            "    JSON_VALUE(b.payload, '$.runtime.tracker_type') AS tracker_type,",
            "    JSON_VALUE(b.payload, '$.runtime.supervision_version') AS supervision_version,",
            "    JSON_VALUE(b.payload, '$.runtime.trackers_version') AS trackers_version,",
            "    JSON_VALUE(b.payload, '$.runtime.zone_config_version') AS zone_config_version,",
            "    CURRENT_TIMESTAMP AS processing_ts,",
            "    CAST(TO_TIMESTAMP_LTZ(t.capture_ts_ms, 3) AS DATE) AS capture_date,",
            "    t.parse_status AS parse_status,",
            "    ROW_NUMBER() OVER (",
            "      PARTITION BY COALESCE(b.event_id, JSON_VALUE(b.payload, '$.event_id')),",
            "                   COALESCE(t.det_id, CAST(t.track_id AS STRING))",
            "      ORDER BY t.conf DESC, TO_TIMESTAMP_LTZ(t.capture_ts_ms, 3) DESC",
            "    ) AS rn",
            "  FROM rva.bronze_raw AS b,",
            "       LATERAL TABLE(parse_detections(b.payload)) AS t",
            "  WHERE",
            "    JSON_VALUE(b.payload, '$.frame_index') IS NOT NULL",
            "    AND COALESCE(b.event_id, JSON_VALUE(b.payload, '$.event_id')) IS NOT NULL",
            "    AND t.capture_ts_ms > 0",
            "    AND b.camera_id IS NOT NULL",
            "    AND b.store_id IS NOT NULL",
            "    AND t.det_id IS NOT NULL",
            "    AND t.track_id IS NOT NULL",
            "    AND t.global_track_id IS NOT NULL",
            "    AND t.conf IS NOT NULL",
            "    AND t.conf >= 0.15",
            backfillDateFilter,
            ") WHERE parse_status = 'ok' AND rn = 1"
        );

        String insertParseErrorsSql = String.join("\n",
            "INSERT INTO rva.silver_detection_parse_errors",
            "SELECT",
            "  b.schema_version AS schema_version,",
            "  COALESCE(b.event_id, JSON_VALUE(b.payload, '$.event_id')) AS event_id,",
            "  COALESCE(b.pipeline_run_id, JSON_VALUE(b.payload, '$.pipeline_run_id')) AS pipeline_run_id,",
            "  b.store_id AS store_id,",
            "  b.camera_id AS camera_id,",
            "  CAST(JSON_VALUE(b.payload, '$.frame_index') AS BIGINT) AS frame_index,",
            "  CAST(JSON_VALUE(b.payload, '$.source_frame_index') AS BIGINT) AS source_frame_index,",
            "  t.parse_error_reason AS parse_error_reason,",
            "  t.capture_ts_raw AS capture_ts_raw,",
            "  b.payload AS raw_payload,",
            "  CURRENT_TIMESTAMP AS processing_ts",
            "FROM rva.bronze_raw AS b,",
            "     LATERAL TABLE(parse_detections(b.payload)) AS t",
            "WHERE t.parse_status = 'error'",
            backfillDateFilter
        );

        StatementSet statements = tEnv.createStatementSet();
        statements.addInsertSql(insertV2Sql);
        statements.addInsertSql(insertParseErrorsSql);
        statements.execute();
    }

    private static String captureDateFilter(String startDate, String endDate) {
        String captureDateExpr = "CAST(TO_TIMESTAMP_LTZ(t.capture_ts_ms, 3) AS DATE)";
        if (startDate == null || startDate.isBlank()) {
            return "";
        }
        if (endDate == null || endDate.isBlank()) {
            return "    AND " + captureDateExpr + " >= DATE '" + startDate + "'";
        }
        return "    AND " + captureDateExpr + " BETWEEN DATE '" + startDate + "' AND DATE '" + endDate + "'";
    }

    private static String getenv(String k, String def) {
        String v = System.getenv(k);
        return (v == null || v.isEmpty()) ? def : v;
    }

    private static void applyJobParallelism(
        TableEnvironment tEnv,
        String envKey,
        String defaultParallelism
    ) {
        tEnv.getConfig().set(
            "table.exec.resource.default-parallelism",
            getenv(envKey, defaultParallelism)
        );
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
