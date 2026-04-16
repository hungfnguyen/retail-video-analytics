package org.rva.silver.udf;

import org.apache.flink.shaded.jackson2.com.fasterxml.jackson.databind.JsonNode;
import org.apache.flink.shaded.jackson2.com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.flink.table.annotation.DataTypeHint;
import org.apache.flink.table.annotation.FunctionHint;
import org.apache.flink.table.functions.TableFunction;
import org.apache.flink.types.Row;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;

/**
 * UDTF: parse JSON payload của Bronze để tạo ra nhiều dòng detection.
 * Trả về các cột đã chuẩn hóa, tránh phụ thuộc FROM_JSON/JSON_TABLE.
 */
@FunctionHint(output = @DataTypeHint(
    "ROW<" +
        "capture_ts_ms BIGINT, " +
        "img_w INT, img_h INT, " +
        "det_id STRING, class_name STRING, class_id INT, conf DOUBLE, " +
        "bbox_x1 INT, bbox_y1 INT, bbox_x2 INT, bbox_y2 INT, " +
        "track_id BIGINT>"))
public class ParseDetections extends TableFunction<Row> {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    public void eval(String payload) {
        if (payload == null || payload.isEmpty()) {
            return;
        }
        try {
            JsonNode root = MAPPER.readTree(payload);

            long captureMs = parseCaptureMs(root.path("capture_ts").asText(null));
            int imgW = root.path("image_size").path("width").asInt(0);
            int imgH = root.path("image_size").path("height").asInt(0);

            JsonNode detections = root.path("detections");
            if (detections != null && detections.isArray()) {
                for (JsonNode det : detections) {
                    String detId = text(det, "det_id");
                    String className = normalizeClassName(text(det, "class"));
                    int classId = det.path("class_id").asInt(-1);
                    double confRaw = det.path("conf").isNumber() ? det.get("conf").asDouble() : Double.NaN;
                    double conf = Double.isNaN(confRaw) ? 0.0 : Math.max(0.0, Math.min(1.0, confRaw));

                    JsonNode bbox = det.path("bbox");
                    int x1 = Math.max(0, asInt(bbox, "x1"));
                    int y1 = Math.max(0, asInt(bbox, "y1"));
                    int x2 = Math.max(0, asInt(bbox, "x2"));
                    int y2 = Math.max(0, asInt(bbox, "y2"));
                    // Đảm bảo x2>=x1, y2>=y1
                    if (x2 < x1) x2 = x1;
                    if (y2 < y1) y2 = y1;

                    Long trackId = det.hasNonNull("track_id") ? det.get("track_id").asLong() : null;

                    Row out = Row.of(
                        captureMs, imgW, imgH,
                        detId, className, classId, conf,
                        x1, y1, x2, y2,
                        trackId
                    );
                    collect(out);
                }
            }
        } catch (Exception ignore) {
            // Bỏ qua record lỗi parse để không làm hỏng pipeline
        }
    }

    private static String text(JsonNode node, String field) {
        JsonNode v = node.get(field);
        return v == null || v.isNull() ? null : v.asText();
    }

    private static String normalizeClassName(String s) {
        if (s == null) return "person";
        String v = s.trim();
        if (v.isEmpty()) return "person";
        if ("none".equalsIgnoreCase(v) || "null".equalsIgnoreCase(v)) return "person";
        return v;
    }

    private static int asInt(JsonNode node, String field) {
        if (node == null) return 0;
        JsonNode v = node.get(field);
        if (v == null || v.isNull()) return 0;
        // Giá trị bbox có thể là double; ép kiểu an toàn
        if (v.isNumber()) {
            return (int) Math.round(v.asDouble());
        }
        try {
            return (int) Math.round(Double.parseDouble(v.asText()));
        } catch (Exception e) {
            return 0;
        }
    }

    private static long parseCaptureMs(String ts) {
        if (ts == null) return System.currentTimeMillis();
        try {
            return Instant.parse(ts).toEpochMilli();
        } catch (DateTimeParseException ignore) {
        }
        try {
            return OffsetDateTime.parse(ts).toInstant().toEpochMilli();
        } catch (DateTimeParseException ignore) {
        }
        return System.currentTimeMillis();
    }
}
