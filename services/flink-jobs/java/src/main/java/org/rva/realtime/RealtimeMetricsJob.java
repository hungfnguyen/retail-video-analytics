package org.rva.realtime;

import org.apache.flink.api.common.eventtime.SerializableTimestampAssigner;
import org.apache.flink.connector.base.DeliveryGuarantee;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.serialization.SimpleStringSchema;
import org.apache.flink.api.common.state.StateTtlConfig;
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.api.common.time.Time;
import org.apache.flink.api.common.typeinfo.Types;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.connector.pulsar.sink.PulsarSink;
import org.apache.flink.connector.pulsar.source.PulsarSource;
import org.apache.flink.connector.pulsar.source.enumerator.cursor.StartCursor;
import org.apache.flink.shaded.jackson2.com.fasterxml.jackson.databind.JsonNode;
import org.apache.flink.shaded.jackson2.com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.flink.streaming.api.CheckpointingMode;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.datastream.SingleOutputStreamOperator;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.functions.KeyedProcessFunction;
import org.apache.flink.streaming.api.functions.ProcessFunction;
import org.apache.flink.streaming.api.functions.sink.RichSinkFunction;
import org.apache.flink.util.Collector;
import org.apache.flink.util.OutputTag;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import redis.clients.jedis.Jedis;
import redis.clients.jedis.JedisPool;
import redis.clients.jedis.JedisPoolConfig;

import java.time.Duration;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * RealtimeMetricsJob - Flink DataStream API for low-latency realtime serving.
 *
 * Reads detection events directly from Pulsar, validates them, deduplicates by
 * event_id, writes live state to Redis, and publishes invalid events to DLQ.
 */
public class RealtimeMetricsJob {

    private static final Logger LOG = LoggerFactory.getLogger(RealtimeMetricsJob.class);

    private static final OutputTag<String> DLQ_TAG =
            new OutputTag<>("dlq-events", Types.STRING);

    private static final int GRID_W = 64;
    private static final int GRID_H = 48;
    private static final ObjectMapper MAPPER = new ObjectMapper();

    static class ParsedEvent {
        String eventId;
        String cameraId;
        String storeId;
        long captureMs;
        long frameIndex;
        int imgW;
        int imgH;
        int personCount;
        int[] gridXs;
        int[] gridYs;
        Long[] trackIds;
        String[] globalTrackIds;
        List<Map<String, Object>> zoneCounts;
        List<Map<String, Object>> lineCrossings;
        double[] bboxXs;
        double[] bboxYs;
        double[] bboxWs;
        double[] bboxHs;
        double[] centroidXs;
        double[] centroidYs;
        double[] confidences;
    }

    static class ParseValidateFunction extends ProcessFunction<String, ParsedEvent>
            implements SerializableTimestampAssigner<ParsedEvent> {

        private final String sourceTopic;

        ParseValidateFunction(String sourceTopic) {
            this.sourceTopic = sourceTopic;
        }

        @Override
        public void processElement(
                String rawJson, Context ctx, Collector<ParsedEvent> out) throws Exception {

            JsonNode root;
            try {
                root = MAPPER.readTree(rawJson);
            } catch (Exception e) {
                ctx.output(DLQ_TAG, buildDlqEnvelope("unparseable_json", rawJson));
                return;
            }

            String eventId = root.path("event_id").asText("");
            String cameraId = root.path("source").path("camera_id").asText("");
            String storeId = root.path("source").path("store_id").asText("");

            if (eventId.isEmpty()) {
                ctx.output(DLQ_TAG, buildDlqEnvelope("missing_event_id", rawJson));
                return;
            }
            if (cameraId.isEmpty()) {
                ctx.output(DLQ_TAG, buildDlqEnvelope("missing_camera_id", rawJson));
                return;
            }
            if (storeId.isEmpty()) {
                ctx.output(DLQ_TAG, buildDlqEnvelope("missing_store_id", rawJson));
                return;
            }

            String captureTsStr = root.path("capture_ts").asText(null);
            long captureMs;
            try {
                captureMs = parseCaptureMs(captureTsStr);
            } catch (Exception e) {
                ctx.output(DLQ_TAG, buildDlqEnvelope("invalid_capture_ts", rawJson));
                return;
            }

            int imgW = root.path("image_size").path("width").asInt(0);
            int imgH = root.path("image_size").path("height").asInt(0);
            if (imgW <= 0 || imgH <= 0) {
                ctx.output(DLQ_TAG, buildDlqEnvelope("invalid_image_size", rawJson));
                return;
            }
            long frameIndex = root.path("frame_index").asLong(0L);

            JsonNode detections = root.path("detections");
            int count = 0;
            List<Integer> gridXList = new ArrayList<>();
            List<Integer> gridYList = new ArrayList<>();
            List<Long> trackIdList = new ArrayList<>();
            List<String> globalTrackIdList = new ArrayList<>();
            List<Double> bboxXList = new ArrayList<>();
            List<Double> bboxYList = new ArrayList<>();
            List<Double> bboxWList = new ArrayList<>();
            List<Double> bboxHList = new ArrayList<>();
            List<Double> centroidXList = new ArrayList<>();
            List<Double> centroidYList = new ArrayList<>();
            List<Double> confidenceList = new ArrayList<>();

            if (detections != null && detections.isArray()) {
                for (JsonNode det : detections) {
                    if (det == null || det.isNull()) {
                        continue;
                    }

                    int classId = det.path("class_id").asInt(-1);
                    if (classId != 0) {
                        continue;
                    }

                    double conf = det.path("conf").asDouble(0.0);
                    if (conf < 0.4) {
                        continue;
                    }

                    JsonNode cn = det.path("centroid_norm");
                    double nx = clampDouble(cn.path("x").asDouble(0.0), 0.0, 1.0);
                    double ny = clampDouble(cn.path("y").asDouble(0.0), 0.0, 1.0);
                    int gx = clamp((int) (nx * GRID_W), 0, GRID_W - 1);
                    int gy = clamp((int) (ny * GRID_H), 0, GRID_H - 1);

                    JsonNode bn = det.path("bbox_norm");
                    double bx = clampDouble(bn.path("x").asDouble(0.0), 0.0, 1.0);
                    double by = clampDouble(bn.path("y").asDouble(0.0), 0.0, 1.0);
                    double bw = clampDouble(bn.path("w").asDouble(0.0), 0.0, 1.0);
                    double bh = clampDouble(bn.path("h").asDouble(0.0), 0.0, 1.0);
                    if (bw <= 0.0 || bh <= 0.0) {
                        continue;
                    }

                    Long trackId = null;
                    JsonNode tid = det.get("track_id");
                    if (tid != null && !tid.isNull() && tid.isNumber()) {
                        trackId = tid.asLong();
                    }
                    String globalTrackId = null;
                    JsonNode gid = det.get("global_track_id");
                    if (gid != null && !gid.isNull() && gid.isTextual()) {
                        globalTrackId = gid.asText();
                    }

                    count++;
                    gridXList.add(gx);
                    gridYList.add(gy);
                    trackIdList.add(trackId);
                    globalTrackIdList.add(globalTrackId);
                    bboxXList.add(bx);
                    bboxYList.add(by);
                    bboxWList.add(bw);
                    bboxHList.add(bh);
                    centroidXList.add(nx);
                    centroidYList.add(ny);
                    confidenceList.add(conf);
                }
            }

            ParsedEvent evt = new ParsedEvent();
            evt.eventId = eventId;
            evt.cameraId = cameraId;
            evt.storeId = storeId;
            evt.captureMs = captureMs;
            evt.frameIndex = frameIndex;
            evt.imgW = imgW;
            evt.imgH = imgH;
            evt.personCount = count;
            evt.gridXs = gridXList.stream().mapToInt(Integer::intValue).toArray();
            evt.gridYs = gridYList.stream().mapToInt(Integer::intValue).toArray();
            evt.trackIds = trackIdList.toArray(new Long[0]);
            evt.globalTrackIds = globalTrackIdList.toArray(new String[0]);
            evt.zoneCounts = parseZoneCounts(root.path("zone_counts"));
            evt.lineCrossings = parseLineCrossings(root.path("line_crossings"));
            evt.bboxXs = toDoubleArray(bboxXList);
            evt.bboxYs = toDoubleArray(bboxYList);
            evt.bboxWs = toDoubleArray(bboxWList);
            evt.bboxHs = toDoubleArray(bboxHList);
            evt.centroidXs = toDoubleArray(centroidXList);
            evt.centroidYs = toDoubleArray(centroidYList);
            evt.confidences = toDoubleArray(confidenceList);

            out.collect(evt);
        }

        @Override
        public long extractTimestamp(ParsedEvent evt, long recordTimestamp) {
            return evt.captureMs;
        }

        private String buildDlqEnvelope(String reason, String rawJson) {
            Map<String, Object> envelope = new LinkedHashMap<>();
            envelope.put("schema_version", "1.0");
            envelope.put("event_type", "invalid_detection_event");
            envelope.put("reason", reason);
            envelope.put("source_topic", sourceTopic);
            envelope.put("failed_at", Instant.now().toString());
            envelope.put("raw_payload", rawJson);
            try {
                return MAPPER.writeValueAsString(envelope);
            } catch (Exception e) {
                return "{\"schema_version\":\"1.0\",\"event_type\":\"invalid_detection_event\",\"reason\":\"dlq_envelope_encode_failed\"}";
            }
        }

        private static long parseCaptureMs(String ts) {
            if (ts == null || ts.isBlank()) {
                throw new IllegalArgumentException("capture_ts is missing");
            }
            try {
                return Instant.parse(ts).toEpochMilli();
            } catch (DateTimeParseException ignore) {
            }
            return OffsetDateTime.parse(ts).toInstant().toEpochMilli();
        }

        private static int clamp(int val, int min, int max) {
            return Math.max(min, Math.min(max, val));
        }

        private static double clampDouble(double val, double min, double max) {
            return Math.max(min, Math.min(max, val));
        }

        private static List<Map<String, Object>> parseZoneCounts(JsonNode zoneCounts) {
            List<Map<String, Object>> values = new ArrayList<>();
            if (zoneCounts == null || !zoneCounts.isArray()) {
                return values;
            }
            for (JsonNode zone : zoneCounts) {
                String zoneId = zone.path("zone_id").asText("");
                if (zoneId.isEmpty()) {
                    continue;
                }
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("zone_id", zoneId);
                item.put("zone_type", zone.path("zone_type").asText("unknown"));
                item.put("count", zone.path("count").asInt(0));
                values.add(item);
            }
            return values;
        }

        private static List<Map<String, Object>> parseLineCrossings(JsonNode lineCrossings) {
            List<Map<String, Object>> values = new ArrayList<>();
            if (lineCrossings == null || !lineCrossings.isArray()) {
                return values;
            }
            for (JsonNode line : lineCrossings) {
                String lineId = line.path("line_id").asText("");
                String direction = line.path("direction").asText("");
                if (lineId.isEmpty() || direction.isEmpty()) {
                    continue;
                }
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("line_id", lineId);
                item.put("line_type", line.path("line_type").asText("crossing"));
                item.put("direction", direction);
                item.put("track_id", line.path("track_id").isNumber() ? line.path("track_id").asLong() : null);
                item.put("global_track_id", line.path("global_track_id").isTextual() ? line.path("global_track_id").asText() : null);
                values.add(item);
            }
            return values;
        }

        private static double[] toDoubleArray(List<Double> values) {
            double[] arr = new double[values.size()];
            for (int i = 0; i < values.size(); i++) {
                arr[i] = values.get(i);
            }
            return arr;
        }
    }

    static class DeduplicateByEventIdFunction
            extends KeyedProcessFunction<String, ParsedEvent, ParsedEvent> {

        private transient ValueState<Boolean> seenState;

        @Override
        public void open(Configuration parameters) {
            StateTtlConfig ttlConfig = StateTtlConfig
                    .newBuilder(Time.minutes(10))
                    .setUpdateType(StateTtlConfig.UpdateType.OnCreateAndWrite)
                    .setStateVisibility(StateTtlConfig.StateVisibility.NeverReturnExpired)
                    .build();

            ValueStateDescriptor<Boolean> descriptor =
                    new ValueStateDescriptor<>("seen-event-id", Boolean.class);
            descriptor.enableTimeToLive(ttlConfig);
            seenState = getRuntimeContext().getState(descriptor);
        }

        @Override
        public void processElement(
                ParsedEvent evt, Context ctx, Collector<ParsedEvent> out) throws Exception {
            if (Boolean.TRUE.equals(seenState.value())) {
                LOG.debug("Skipping duplicate event_id={}", evt.eventId);
                return;
            }
            seenState.update(true);
            out.collect(evt);
        }
    }

    static class RealtimeRedisSink extends RichSinkFunction<ParsedEvent> {

        private static final int HEATMAP_EXPIRE_SEC = 60;
        private static final int COUNT_EXPIRE_SEC = 5;
        private static final int FRAME_EXPIRE_SEC = 10;
        private static final int TRACK_EXPIRE_SEC = 30;
        private static final int ZONE_EXPIRE_SEC = 10;
        private static final int QUEUE_EXPIRE_SEC = 10;
        private static final int LINE_EXPIRE_SEC = 300;

        private transient JedisPool pool;

        @Override
        public void open(Configuration parameters) {
            String host = getenv("REDIS_HOST", "redis");
            int port = Integer.parseInt(getenv("REDIS_PORT", "6379"));
            String password = getenv("REDIS_PASSWORD", "");

            JedisPoolConfig cfg = new JedisPoolConfig();
            cfg.setMaxTotal(8);
            cfg.setMaxIdle(4);
            cfg.setMinIdle(1);
            cfg.setMaxWait(Duration.ofSeconds(2));

            if (password != null && !password.isEmpty()) {
                pool = new JedisPool(cfg, host, port, 2000, password);
            } else {
                pool = new JedisPool(cfg, host, port, 2000);
            }
            LOG.info("Redis sink connected to {}:{}", host, port);
        }

        @Override
        public void invoke(ParsedEvent evt, Context context) {
            String cameraId = evt.cameraId;
            if (cameraId == null || cameraId.isEmpty()) {
                return;
            }

            try (Jedis jedis = pool.getResource()) {
                jedis.setex("stats:count:" + cameraId, COUNT_EXPIRE_SEC,
                        String.valueOf(evt.personCount));

                String ts = Instant.ofEpochMilli(evt.captureMs).toString();
                jedis.setex("live:frame:" + cameraId, FRAME_EXPIRE_SEC,
                        buildLiveFrameSnapshot(evt, ts));

                String heatKey = "heatmap:live:" + cameraId;
                for (int i = 0; i < evt.gridXs.length; i++) {
                    jedis.zincrby(heatKey, 1.0,
                            evt.gridXs[i] + "," + evt.gridYs[i]);
                }
                jedis.expire(heatKey, HEATMAP_EXPIRE_SEC);

                for (int i = 0; i < evt.trackIds.length; i++) {
                    if (evt.trackIds[i] == null) {
                        continue;
                    }
                    String trackKey = "track:active:" + cameraId + ":" + evt.trackIds[i];
                    Map<String, String> fields = new HashMap<>();
                    fields.put("event_id", evt.eventId);
                    fields.put("store_id", evt.storeId);
                    fields.put("last_seen", ts);
                    fields.put("grid_x", String.valueOf(evt.gridXs[i]));
                    fields.put("grid_y", String.valueOf(evt.gridYs[i]));
                    fields.put("bbox_x", String.valueOf(evt.bboxXs[i]));
                    fields.put("bbox_y", String.valueOf(evt.bboxYs[i]));
                    fields.put("bbox_w", String.valueOf(evt.bboxWs[i]));
                    fields.put("bbox_h", String.valueOf(evt.bboxHs[i]));
                    fields.put("confidence", String.valueOf(evt.confidences[i]));
                    if (i < evt.globalTrackIds.length && evt.globalTrackIds[i] != null) {
                        fields.put("global_track_id", evt.globalTrackIds[i]);
                    }
                    jedis.hset(trackKey, fields);
                    jedis.expire(trackKey, TRACK_EXPIRE_SEC);
                }

                writeZoneCounts(jedis, evt, ts);
                writeLineCrossings(jedis, evt);
            } catch (Exception e) {
                LOG.warn("Redis write failed for camera {}: {}", cameraId, e.toString());
            }
        }

        private void writeZoneCounts(Jedis jedis, ParsedEvent evt, String ts) {
            if (evt.zoneCounts == null || evt.zoneCounts.isEmpty()) {
                return;
            }
            String zoneKey = "zone:count:" + evt.cameraId;
            Map<String, String> zoneFields = new HashMap<>();
            for (Map<String, Object> zone : evt.zoneCounts) {
                String zoneId = String.valueOf(zone.get("zone_id"));
                String zoneType = String.valueOf(zone.getOrDefault("zone_type", "unknown"));
                String count = String.valueOf(zone.getOrDefault("count", 0));
                if (zoneId == null || zoneId.isEmpty() || "null".equals(zoneId)) {
                    continue;
                }
                zoneFields.put(zoneId, count);
                if ("queue".equals(zoneType)) {
                    String queueKey = "queue:live:" + evt.cameraId + ":" + zoneId;
                    Map<String, String> queueFields = new HashMap<>();
                    queueFields.put("zone_id", zoneId);
                    queueFields.put("zone_type", zoneType);
                    queueFields.put("current_count", count);
                    queueFields.put("last_update_ts", ts);
                    jedis.hset(queueKey, queueFields);
                    jedis.expire(queueKey, QUEUE_EXPIRE_SEC);
                }
            }
            if (!zoneFields.isEmpty()) {
                jedis.hset(zoneKey, zoneFields);
                jedis.expire(zoneKey, ZONE_EXPIRE_SEC);
            }
        }

        private void writeLineCrossings(Jedis jedis, ParsedEvent evt) {
            if (evt.lineCrossings == null || evt.lineCrossings.isEmpty()) {
                return;
            }
            for (Map<String, Object> crossing : evt.lineCrossings) {
                String lineId = String.valueOf(crossing.get("line_id"));
                String direction = String.valueOf(crossing.get("direction"));
                if (lineId == null || lineId.isEmpty() || "null".equals(lineId)
                        || direction == null || direction.isEmpty() || "null".equals(direction)) {
                    continue;
                }
                String lineKey = "line:count:" + evt.cameraId + ":" + lineId + ":5m";
                jedis.hincrBy(lineKey, direction + "_count", 1L);
                jedis.expire(lineKey, LINE_EXPIRE_SEC);
            }
        }

        @Override
        public void close() {
            if (pool != null) {
                pool.close();
            }
        }

        private String buildLiveFrameSnapshot(ParsedEvent evt, String captureTs) throws Exception {
            Map<String, Object> frame = new LinkedHashMap<>();
            frame.put("schema_version", "1.0");
            frame.put("event_id", evt.eventId);
            frame.put("camera_id", evt.cameraId);
            frame.put("store_id", evt.storeId);
            frame.put("frame_index", evt.frameIndex);
            frame.put("capture_ts", captureTs);

            Map<String, Object> imageSize = new LinkedHashMap<>();
            imageSize.put("width", evt.imgW);
            imageSize.put("height", evt.imgH);
            frame.put("image_size", imageSize);

            List<Map<String, Object>> detections = new ArrayList<>();
            for (int i = 0; i < evt.gridXs.length; i++) {
                Map<String, Object> det = new LinkedHashMap<>();
                det.put("track_id", evt.trackIds[i]);
                if (i < evt.globalTrackIds.length) {
                    det.put("global_track_id", evt.globalTrackIds[i]);
                }
                det.put("label", "person");
                det.put("confidence", evt.confidences[i]);

                Map<String, Object> bboxNorm = new LinkedHashMap<>();
                bboxNorm.put("x", evt.bboxXs[i]);
                bboxNorm.put("y", evt.bboxYs[i]);
                bboxNorm.put("w", evt.bboxWs[i]);
                bboxNorm.put("h", evt.bboxHs[i]);
                det.put("bbox_norm", bboxNorm);

                Map<String, Object> centroidNorm = new LinkedHashMap<>();
                centroidNorm.put("x", evt.centroidXs[i]);
                centroidNorm.put("y", evt.centroidYs[i]);
                det.put("centroid_norm", centroidNorm);

                det.put("grid_x", evt.gridXs[i]);
                det.put("grid_y", evt.gridYs[i]);
                detections.add(det);
            }
            frame.put("detections", detections);
            frame.put("zone_counts", evt.zoneCounts == null ? List.of() : evt.zoneCounts);
            frame.put("line_crossings", evt.lineCrossings == null ? List.of() : evt.lineCrossings);
            return MAPPER.writeValueAsString(frame);
        }
    }

    public static void main(String[] args) throws Exception {
        String pulsarServiceUrl = getenv("PULSAR_SERVICE_URL", "pulsar://pulsar-broker:6650");
        String pulsarAdminUrl = getenv("PULSAR_ADMIN_URL", "http://pulsar-broker:8080");
        String pulsarTopic = getenv("PULSAR_TOPIC", "persistent://retail/metadata/events");
        String dlqTopic = getenv("PULSAR_DLQ_TOPIC", "persistent://retail/metadata/dlq-events");

        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.enableCheckpointing(10_000L, CheckpointingMode.EXACTLY_ONCE);
        env.getCheckpointConfig().setMinPauseBetweenCheckpoints(5_000L);

        PulsarSource<String> pulsarSource = PulsarSource.builder()
                .setServiceUrl(pulsarServiceUrl)
                .setAdminUrl(pulsarAdminUrl)
                .setStartCursor(StartCursor.latest())
                .setTopics(pulsarTopic)
                .setDeserializationSchema(new SimpleStringSchema())
                .setSubscriptionName("flink-realtime-sub")
                .build();

        DataStream<String> rawStream = env.fromSource(
                pulsarSource,
                WatermarkStrategy.noWatermarks(),
                "pulsar-source"
        );

        ParseValidateFunction parser = new ParseValidateFunction(pulsarTopic);

        WatermarkStrategy<ParsedEvent> watermarkStrategy = WatermarkStrategy
                .<ParsedEvent>forBoundedOutOfOrderness(Duration.ofSeconds(5))
                .withTimestampAssigner(parser)
                .withIdleness(Duration.ofSeconds(30));

        SingleOutputStreamOperator<ParsedEvent> parsedStream = rawStream
                .process(parser)
                .name("parse-validate")
                .assignTimestampsAndWatermarks(watermarkStrategy)
                .name("assign-event-time");

        DataStream<String> dlqStream = parsedStream.getSideOutput(DLQ_TAG);

        parsedStream
                .keyBy(evt -> evt.eventId)
                .process(new DeduplicateByEventIdFunction())
                .name("dedup-event-id")
                .addSink(new RealtimeRedisSink())
                .name("redis-sink");

        PulsarSink<String> dlqSink = PulsarSink.builder()
                .setServiceUrl(pulsarServiceUrl)
                .setAdminUrl(pulsarAdminUrl)
                .setTopics(dlqTopic)
                .setSerializationSchema(new SimpleStringSchema())
                .setDeliveryGuarantee(DeliveryGuarantee.AT_LEAST_ONCE)
                .build();

        dlqStream
                .sinkTo(dlqSink)
                .name("dlq-pulsar-sink");

        env.execute("RealtimeMetricsJob");
    }

    private static String getenv(String k, String def) {
        String v = System.getenv(k);
        return (v == null || v.isEmpty()) ? def : v;
    }
}
