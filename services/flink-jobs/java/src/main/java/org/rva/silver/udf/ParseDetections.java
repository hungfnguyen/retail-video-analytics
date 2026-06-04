package org.rva.silver.udf;

import org.apache.flink.shaded.jackson2.com.fasterxml.jackson.databind.JsonNode;
import org.apache.flink.shaded.jackson2.com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.flink.metrics.Counter;
import org.apache.flink.table.annotation.DataTypeHint;
import org.apache.flink.table.annotation.FunctionHint;
import org.apache.flink.table.functions.FunctionContext;
import org.apache.flink.table.functions.TableFunction;
import org.apache.flink.types.Row;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;

/**
 * UDTF: parse Bronze JSON payload into one row per detection.
 *
 * The first fields preserve the legacy Silver contract. The additional fields
 * carry the rebuilt Supervision pipeline facts: raw tracker ID, stable global
 * ID, bottom-center anchor, primary semantic zone, and queue state.
 */
@FunctionHint(output = @DataTypeHint(
    "ROW<" +
        "capture_ts_ms BIGINT, " +
        "img_w INT, img_h INT, " +
        "det_id STRING, class_name STRING, class_id INT, conf DOUBLE, " +
        "bbox_x1 INT, bbox_y1 INT, bbox_x2 INT, bbox_y2 INT, " +
        "track_id BIGINT, raw_track_id BIGINT, global_track_id STRING, " +
        "track_state STRING, is_predicted BOOLEAN, " +
        "anchor_type STRING, anchor_x INT, anchor_y INT, " +
        "anchor_x_norm DOUBLE, anchor_y_norm DOUBLE, " +
        "primary_zone_id STRING, primary_zone_type STRING, " +
        "in_queue BOOLEAN, queue_zone_id STRING>"))
public class ParseDetections extends TableFunction<Row> {

    private static final Logger LOG = LoggerFactory.getLogger(ParseDetections.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private transient Counter invalidRecordCounter;

    @Override
    public void open(FunctionContext context) {
        invalidRecordCounter = context.getMetricGroup()
                .counter("detection_parse_invalid_total");
    }

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
                    if (x2 < x1) x2 = x1;
                    if (y2 < y1) y2 = y1;

                    Long trackId = asLongOrNull(det.get("track_id"));
                    Long rawTrackId = asLongOrNull(det.get("raw_track_id"));
                    String globalTrackId = text(det, "global_track_id");
                    String trackState = text(det, "track_state");
                    boolean isPredicted = asBoolean(det.get("is_predicted"));

                    JsonNode anchor = det.path("anchor");
                    String anchorType = text(anchor, "type");
                    int anchorX = asInt(anchor, "x");
                    int anchorY = asInt(anchor, "y");
                    double anchorXNorm = asDouble(anchor, "x_norm");
                    double anchorYNorm = asDouble(anchor, "y_norm");

                    ZoneFields zone = primaryZone(det.path("zones"));
                    JsonNode queue = det.path("queue");
                    boolean inQueue = asBoolean(queue.get("in_queue"));
                    String queueZoneId = text(queue, "queue_zone_id");

                    collect(Row.of(
                        captureMs, imgW, imgH,
                        detId, className, classId, conf,
                        x1, y1, x2, y2,
                        trackId, rawTrackId, globalTrackId,
                        trackState, isPredicted,
                        anchorType, anchorX, anchorY,
                        anchorXNorm, anchorYNorm,
                        zone.zoneId, zone.zoneType,
                        inQueue, queueZoneId
                    ));
                }
            }
        } catch (Exception e) {
            LOG.warn("Failed to parse detection payload ({}), skipping record", e.toString());
            if (invalidRecordCounter != null) {
                invalidRecordCounter.inc();
            }
        }
    }

    private static ZoneFields primaryZone(JsonNode zones) {
        if (zones == null || !zones.isArray() || zones.size() == 0) {
            return new ZoneFields(null, null);
        }
        JsonNode fallback = null;
        for (JsonNode zone : zones) {
            if (zone == null || zone.isNull()) {
                continue;
            }
            if (fallback == null) {
                fallback = zone;
            }
            if (asBoolean(zone.get("is_primary"))) {
                return new ZoneFields(text(zone, "zone_id"), text(zone, "zone_type"));
            }
        }
        return fallback == null
                ? new ZoneFields(null, null)
                : new ZoneFields(text(fallback, "zone_id"), text(fallback, "zone_type"));
    }

    private static String text(JsonNode node, String field) {
        if (node == null || node.isNull()) {
            return null;
        }
        JsonNode v = node.get(field);
        if (v == null || v.isNull()) {
            return null;
        }
        String s = v.asText();
        return s == null || s.isBlank() ? null : s;
    }

    private static String normalizeClassName(String s) {
        if (s == null) return "person";
        String v = s.trim();
        if (v.isEmpty()) return "person";
        if ("none".equalsIgnoreCase(v) || "null".equalsIgnoreCase(v)) return "person";
        return v;
    }

    private static int asInt(JsonNode node, String field) {
        if (node == null || node.isNull()) return 0;
        JsonNode v = node.get(field);
        if (v == null || v.isNull()) return 0;
        if (v.isNumber()) {
            return (int) Math.round(v.asDouble());
        }
        try {
            return (int) Math.round(Double.parseDouble(v.asText()));
        } catch (Exception e) {
            return 0;
        }
    }

    private static double asDouble(JsonNode node, String field) {
        if (node == null || node.isNull()) return 0.0;
        JsonNode v = node.get(field);
        if (v == null || v.isNull()) return 0.0;
        if (v.isNumber()) {
            return v.asDouble();
        }
        try {
            return Double.parseDouble(v.asText());
        } catch (Exception e) {
            return 0.0;
        }
    }

    private static Long asLongOrNull(JsonNode node) {
        if (node == null || node.isNull()) {
            return null;
        }
        if (node.isNumber()) {
            return node.asLong();
        }
        String raw = node.asText(null);
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return Long.parseLong(raw);
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static boolean asBoolean(JsonNode node) {
        if (node == null || node.isNull()) {
            return false;
        }
        if (node.isBoolean()) {
            return node.asBoolean();
        }
        String raw = node.asText("");
        return "1".equals(raw) || "true".equalsIgnoreCase(raw) || "yes".equalsIgnoreCase(raw);
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

    private static class ZoneFields {
        final String zoneId;
        final String zoneType;

        ZoneFields(String zoneId, String zoneType) {
            this.zoneId = zoneId;
            this.zoneType = zoneType;
        }
    }
}
