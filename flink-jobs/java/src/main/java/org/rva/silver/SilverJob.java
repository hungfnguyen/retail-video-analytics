package org.rva.silver;

import org.apache.flink.table.api.EnvironmentSettings;
import org.apache.flink.table.api.TableEnvironment;
import org.rva.silver.udf.ParseDetections;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

public class SilverJob {
    public static void main(String[] args) throws Exception {
        EnvironmentSettings settings = EnvironmentSettings.newInstance()
            .inStreamingMode()
            .build();
        TableEnvironment tEnv = TableEnvironment.create(settings);

        // Đăng ký UDTF parse JSON
        tEnv.createTemporarySystemFunction("parse_detections", ParseDetections.class);

        // Lấy cấu hình từ ENV (không hardcode secrets)
        Map<String, String> cfg = new LinkedHashMap<>();
        cfg.put("type", "iceberg");
        cfg.put("catalog-impl", "org.apache.iceberg.rest.RESTCatalog");
        cfg.put("uri", getenv("ICEBERG_REST_URI", "http://iceberg-rest:8181"));
        cfg.put("warehouse", ensureWarehouseSuffix(getenv("ICEBERG_WAREHOUSE", "s3://warehouse"), "/iceberg"));
        cfg.put("io-impl", "org.apache.iceberg.aws.s3.S3FileIO");
        cfg.put("s3.endpoint", getenv("S3_ENDPOINT", "http://minio:9000"));
        cfg.put("s3.path-style-access", getenv("S3_PATH_STYLE", "true"));
        cfg.put("s3.region", getenv("S3_REGION", "us-east-1"));

        String accessKey = firstNotBlank(System.getenv("MINIO_ROOT_USER"), System.getenv("AWS_ACCESS_KEY_ID"));
        String secretKey = firstNotBlank(System.getenv("MINIO_ROOT_PASSWORD"), System.getenv("AWS_SECRET_ACCESS_KEY"));
        if (accessKey != null) cfg.put("s3.access-key-id", accessKey);
        if (secretKey != null) cfg.put("s3.secret-access-key", secretKey);

        String catalogSql = "CREATE CATALOG lakehouse WITH (" + cfg.entrySet().stream()
            .map(e -> "'" + e.getKey() + "' = '" + e.getValue() + "'")
            .collect(Collectors.joining(", ")) + ")";

        tEnv.executeSql(catalogSql);
        tEnv.executeSql("USE CATALOG lakehouse");
        tEnv.executeSql("CREATE DATABASE IF NOT EXISTS rva");
        tEnv.executeSql("USE rva");

        // Tạo bảng Silver (Iceberg)
        String createSilver = String.join("\n",
            "CREATE TABLE IF NOT EXISTS rva.silver_detections (",
            "  schema_version  STRING,",
            "  pipeline_run_id STRING,",
            "  store_id        STRING,",
            "  camera_id       STRING,",
            "  frame_index     BIGINT,",
            "  capture_ts      TIMESTAMP(3),",
            "  img_w           INT,",
            "  img_h           INT,",
            "  det_id          STRING,",
            "  class_name      STRING,",
            "  class_id        INT,",
            "  conf            DOUBLE,",
            "  bbox_x1         INT,",
            "  bbox_y1         INT,",
            "  bbox_x2         INT,",
            "  bbox_y2         INT,",
            "  track_id        BIGINT,",
            "  processing_ts   TIMESTAMP_LTZ(3)",
            ") WITH (",
            "  'format-version' = '2',",
            "  'write.format.default' = 'parquet',",
            "  'partitioning' = 'store_id,bucket(16, camera_id),days(capture_ts)'",
            ")"
        );
        tEnv.executeSql(createSilver);

        // Chạy INSERT streaming: dùng UDTF + cleaning giống notebook:
        // - Parse từ JSON (frame_index, pipeline_run_id)
        // - Khử null ở key chính
        // - Lọc nhiễu conf < 0.4
        // - Khử trùng lặp theo (store_id, camera_id, frame_index, det_id/track_id)
        String insertSql = String.join("\n",
            "INSERT INTO rva.silver_detections",
            "SELECT",
            "  schema_version,",
            "  pipeline_run_id,",
            "  store_id,",
            "  camera_id,",
            "  frame_index,",
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
            "  processing_ts",
            "FROM (",
            "  SELECT",
            "    b.schema_version AS schema_version,",
            "    COALESCE(b.pipeline_run_id, JSON_VALUE(b.payload, '$.pipeline_run_id')) AS pipeline_run_id,",
            "    b.store_id AS store_id,",
            "    b.camera_id AS camera_id,",
            "    CAST(JSON_VALUE(b.payload, '$.frame_index') AS BIGINT) AS frame_index,",
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
            "    CURRENT_TIMESTAMP AS processing_ts,",
            "    ROW_NUMBER() OVER (",
            "      PARTITION BY b.store_id,",
            "                   b.camera_id,",
            "                   CAST(JSON_VALUE(b.payload, '$.frame_index') AS BIGINT),",
            "                   COALESCE(t.det_id, CAST(t.track_id AS STRING))",
            "      ORDER BY t.conf DESC, TO_TIMESTAMP_LTZ(t.capture_ts_ms, 3) DESC",
            "    ) AS rn",
            // --- SỬA ĐỔI QUAN TRỌNG TẠI ĐÂY ---
            // Thêm OPTIONS hint để kích hoạt chế độ Streaming đọc từ Iceberg
            "  FROM rva.bronze_raw /*+ OPTIONS('streaming'='true', 'monitor-interval'='1s') */ AS b,",
            "       LATERAL TABLE(parse_detections(b.payload)) AS t",
            "  WHERE",
            "    JSON_VALUE(b.payload, '$.frame_index') IS NOT NULL",
            "    AND t.capture_ts_ms IS NOT NULL",
            "    AND b.camera_id IS NOT NULL",
            "    AND b.store_id IS NOT NULL",
            "    AND t.det_id IS NOT NULL",
            "    AND t.track_id IS NOT NULL",
            "    AND t.conf IS NOT NULL",
            "    AND t.conf >= 0.4",
            ") WHERE rn = 1"
        );

        // Gửi job (streaming) – để Detached mode khi submit qua 'flink run -d'
        tEnv.executeSql(insertSql);

        // Không block; khi submit bằng -d job sẽ chạy nền.
    }

    private static String getenv(String k, String def) {
        String v = System.getenv(k);
        return (v == null || v.isEmpty()) ? def : v;
    }

    private static String firstNotBlank(String a, String b) {
        if (a != null && !a.isBlank()) return a;
        if (b != null && !b.isBlank()) return b;
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
