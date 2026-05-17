package org.rva.realtime;

import org.apache.flink.api.common.eventtime.SerializableTimestampAssigner;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.typeinfo.Types;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.shaded.jackson2.com.fasterxml.jackson.databind.JsonNode;
import org.apache.flink.shaded.jackson2.com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.flink.streaming.api.CheckpointingMode;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.datastream.SingleOutputStreamOperator;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
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
import java.time.format.DateTimeParseException;
import java.util.HashMap;
import java.util.Map;

/**
 * RealtimeMetricsJob — Flink DataStream API for low-latency realtime serving.
 *
 * Reads detection events directly from Pulsar (no Iceberg wait), parses
 * JSON, validates, routes invalid events to DLQ, and writes live metrics
 * to Redis: person count, heatmap grid, and active track positions.
 *
 * Architecture:
 *   Pulsar source (raw JSON string)
 *     -> ProcessFunction: parse + validate + assign event_time
 *          -> valid: Redis sink (live_count, heatmap, track:active)
 *          -> invalid: DLQ side-output -> log (future: Pulsar DLQ sink)
 */
public class RealtimeMetricsJob {

    private static final Logger LOG = LoggerFactory.getLogger(RealtimeMetricsJob.class);

    // Side output tag for invalid / unparseable events
    private static final OutputTag<String> DLQ_TAG =
            new OutputTag<>("dlq-events", Types.STRING);

    // Grid dimensions for live heatmap
    private static final int GRID_W = 64;
    private static final int GRID_H = 48;

    private static final ObjectMapper MAPPER = new ObjectMapper();

    /* ------------------------------------------------------------------ */
    /*  Event POJO                                                         */
    /* ------------------------------------------------------------------ */

    static class ParsedEvent {
        String eventId;
        String cameraId;
        String storeId;
        long captureMs;
        int imgW;
        int imgH;
        int personCount;
        int[] gridXs;
        int[] gridYs;
        Long[] trackIds;
    }

    /* ------------------------------------------------------------------ */
    /*  Parse + Validate ProcessFunction (supports side outputs)           */
    /* ------------------------------------------------------------------ */

    static class ParseValidateFunction extends ProcessFunction<String, ParsedEvent>
            implements SerializableTimestampAssigner<ParsedEvent> {

        @Override
        public void processElement(
                String rawJson, Context ctx, Collector<ParsedEvent> out) throws Exception {

            JsonNode root;
            try {
                root = MAPPER.readTree(rawJson);
            } catch (Exception e) {
                LOG.warn("Unparseable JSON payload, routing to DLQ: {}", e.toString());
                ctx.output(DLQ_TAG, rawJson);
                return;
            }

            String eventId = root.path("event_id").asText("");
            String cameraId = root.path("source").path("camera_id").asText("");
            String storeId = root.path("source").path("store_id").asText("");

            // --- validate required fields ---
            if (eventId.isEmpty() || cameraId.isEmpty()) {
                LOG.warn("Invalid event (missing event_id or camera_id), routing to DLQ");
                ctx.output(DLQ_TAG, rawJson);
                return;
            }

            // --- parse capture_ts ---
            String captureTsStr = root.path("capture_ts").asText(null);
            long captureMs;
            try {
                captureMs = Instant.parse(captureTsStr).toEpochMilli();
            } catch (DateTimeParseException | NullPointerException e) {
                LOG.warn("Unparseable capture_ts '{}', routing to DLQ", captureTsStr);
                ctx.output(DLQ_TAG, rawJson);
                return;
            }

            // --- parse image_size ---
            int imgW = root.path("image_size").path("width").asInt(0);
            int imgH = root.path("image_size").path("height").asInt(0);

            // --- parse detections ---
            JsonNode detections = root.path("detections");
            int count = 0;
            int[] gridXs = new int[0];
            int[] gridYs = new int[0];
            Long[] trackIds = new Long[0];

            if (detections != null && detections.isArray()) {
                int n = detections.size();
                gridXs = new int[n];
                gridYs = new int[n];
                trackIds = new Long[n];
                for (int i = 0; i < n; i++) {
                    JsonNode det = detections.get(i);
                    if (det == null) continue;

                    double conf = det.path("conf").asDouble(0.0);
                    if (conf < 0.4) continue;

                    count++;

                    // compute grid cell from centroid_norm
                    JsonNode cn = det.path("centroid_norm");
                    double nx = cn.path("x").asDouble(0.0);
                    double ny = cn.path("y").asDouble(0.0);
                    int gx = clamp((int) (nx * GRID_W), 0, GRID_W - 1);
                    int gy = clamp((int) (ny * GRID_H), 0, GRID_H - 1);
                    gridXs[i] = gx;
                    gridYs[i] = gy;

                    // track_id
                    JsonNode tid = det.get("track_id");
                    if (tid != null && !tid.isNull() && tid.isNumber()) {
                        trackIds[i] = tid.asLong();
                    }
                }
            }

            ParsedEvent evt = new ParsedEvent();
            evt.eventId = eventId;
            evt.cameraId = cameraId;
            evt.storeId = storeId;
            evt.captureMs = captureMs;
            evt.imgW = imgW;
            evt.imgH = imgH;
            evt.personCount = count;
            evt.gridXs = gridXs;
            evt.gridYs = gridYs;
            evt.trackIds = trackIds;

            out.collect(evt);
        }

        @Override
        public long extractTimestamp(ParsedEvent evt, long recordTimestamp) {
            return evt.captureMs;
        }

        private static int clamp(int val, int min, int max) {
            return Math.max(min, Math.min(max, val));
        }
    }

    /* ------------------------------------------------------------------ */
    /*  Redis Sink — writes live count, heatmap, active tracks            */
    /* ------------------------------------------------------------------ */

    static class RealtimeRedisSink extends RichSinkFunction<ParsedEvent> {

        private static final int HEATMAP_EXPIRE_SEC = 60;
        private static final int COUNT_EXPIRE_SEC = 5;
        private static final int TRACK_EXPIRE_SEC = 30;

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
            if (cameraId == null || cameraId.isEmpty()) return;

            try (Jedis jedis = pool.getResource()) {
                // 1. Live person count
                jedis.setex("stats:count:" + cameraId, COUNT_EXPIRE_SEC,
                        String.valueOf(evt.personCount));

                // 2. Live heatmap — ZINCRBY for each detection grid cell
                String heatKey = "heatmap:live:" + cameraId;
                for (int i = 0; i < evt.gridXs.length; i++) {
                    if (evt.gridXs[i] >= 0 && evt.gridYs[i] >= 0) {
                        jedis.zincrby(heatKey, 1.0,
                                evt.gridXs[i] + "," + evt.gridYs[i]);
                    }
                }
                jedis.expire(heatKey, HEATMAP_EXPIRE_SEC);

                // 3. Active tracks — HSET position per track_id
                String ts = Instant.ofEpochMilli(evt.captureMs).toString();
                for (int i = 0; i < evt.trackIds.length; i++) {
                    if (evt.trackIds[i] == null) continue;
                    String trackKey = "track:active:" + cameraId + ":" + evt.trackIds[i];
                    Map<String, String> fields = new HashMap<>();
                    fields.put("last_seen", ts);
                    fields.put("grid_x", String.valueOf(evt.gridXs[i]));
                    fields.put("grid_y", String.valueOf(evt.gridYs[i]));
                    jedis.hset(trackKey, fields);
                    jedis.expire(trackKey, TRACK_EXPIRE_SEC);
                }
            } catch (Exception e) {
                LOG.warn("Redis write failed for camera {}: {}", cameraId, e.toString());
            }
        }

        @Override
        public void close() {
            if (pool != null) {
                pool.close();
            }
        }

        private static String getenv(String k, String def) {
            String v = System.getenv(k);
            return (v == null || v.isEmpty()) ? def : v;
        }
    }

    /* ------------------------------------------------------------------ */
    /*  DLQ Sink — log invalid events for observability                    */
    /* ------------------------------------------------------------------ */

    static class DlqLogSink extends RichSinkFunction<String> {
        private static final Logger DLQ_LOG = LoggerFactory.getLogger("rva.dlq");

        @Override
        public void invoke(String rawJson, Context context) {
            DLQ_LOG.warn("DLQ event: {}", rawJson.length() > 500
                    ? rawJson.substring(0, 500) + "..."
                    : rawJson);
        }
    }

    /* ------------------------------------------------------------------ */
    /*  Main entry                                                         */
    /* ------------------------------------------------------------------ */

    public static void main(String[] args) throws Exception {
        // --- read configuration from env ---
        String pulsarServiceUrl = getenv("PULSAR_SERVICE_URL", "pulsar://pulsar-broker:6650");
        String pulsarAdminUrl = getenv("PULSAR_ADMIN_URL", "http://pulsar-broker:8080");
        String pulsarTopic = getenv("PULSAR_TOPIC", "persistent://retail/metadata/events");

        // --- Flink environment ---
        StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();
        env.enableCheckpointing(10_000L, CheckpointingMode.EXACTLY_ONCE);
        env.getCheckpointConfig().setMinPauseBetweenCheckpoints(5_000L);

        // --- Pulsar source ---
        org.apache.flink.connector.pulsar.source.PulsarSource<String> pulsarSource =
                org.apache.flink.connector.pulsar.source.PulsarSource.builder()
                        .setServiceUrl(pulsarServiceUrl)
                        .setAdminUrl(pulsarAdminUrl)
                        .setStartCursor(
                                org.apache.flink.connector.pulsar.source.enumerator.cursor
                                        .StartCursor.latest())
                        .setTopics(pulsarTopic)
                        .setDeserializationSchema(
                                new org.apache.flink.api.common.serialization.SimpleStringSchema())
                        .setSubscriptionName("flink-realtime-sub")
                        .build();

        DataStream<String> rawStream = env.fromSource(
                pulsarSource,
                WatermarkStrategy.noWatermarks(),
                "pulsar-source"
        );

        // --- Parse + Validate + Assign Watermarks ---
        ParseValidateFunction parser = new ParseValidateFunction();

        WatermarkStrategy<ParsedEvent> watermarkStrategy = WatermarkStrategy
                .<ParsedEvent>forBoundedOutOfOrderness(Duration.ofSeconds(5))
                .withTimestampAssigner(parser)
                .withIdleness(Duration.ofSeconds(30));

        SingleOutputStreamOperator<ParsedEvent> mainStream = rawStream
                .process(parser)
                .assignTimestampsAndWatermarks(watermarkStrategy)
                .name("parse-validate");

        // --- Side output: DLQ events ---
        DataStream<String> dlqStream = mainStream.getSideOutput(DLQ_TAG);

        // --- Redis sink (valid events) ---
        mainStream
                .addSink(new RealtimeRedisSink())
                .name("redis-sink");

        // --- DLQ sink ---
        dlqStream
                .addSink(new DlqLogSink())
                .name("dlq-sink");

        // --- Execute ---
        env.execute("RealtimeMetricsJob");
    }

    private static String getenv(String k, String def) {
        String v = System.getenv(k);
        return (v == null || v.isEmpty()) ? def : v;
    }
}
