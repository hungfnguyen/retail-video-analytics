# Flink DataStream API vs Table API — Guide for RVA

## 1. Why Two APIs?

Apache Flink cung cấp 2 mô hình lập trình chính:

- **Table API / SQL**: Khai báo (declarative) — viết SQL hoặc fluent Table API, Flink tự tối ưu và chọn execution plan.
- **DataStream API**: Mệnh lệnh (imperative) — viết Java/Python code điều khiển từng operator, state, timer, side output.

Trong RVA, cả 2 API đều được dùng vì mỗi path có yêu cầu khác nhau:

| Path | API | Lý do |
|---|---|---|
| Lakehouse (Bronze→Silver→Gold) | **Table API / SQL** | Iceberg integration native, SQL DDL/DML, schema evolution, exactly-once sinks |
| Realtime (Redis + DLQ) | **DataStream API** | Custom Redis sink, side-output DLQ, fine-grained state, latency thấp |

---

## 2. Table API / SQL — Lakehouse Path

### Khi nào dùng

- Source/Sink là Iceberg, Pulsar, Kafka (có SQL connector)
- Logic chủ yếu là filter, map, join, aggregate (SQL-native)
- Cần exactly-once sink
- Không cần side output hoặc custom sink
- Ưu tiên code ngắn, dễ đọc, dễ bảo trì

### Pattern từ codebase

#### Catalog setup

```java
Map<String, String> cfg = new LinkedHashMap<>();
cfg.put("type", "iceberg");
cfg.put("catalog-impl", "org.apache.iceberg.rest.RESTCatalog");
cfg.put("uri", "http://iceberg-rest:8181");
cfg.put("warehouse", "s3://warehouse/iceberg");
cfg.put("io-impl", "org.apache.iceberg.aws.s3.S3FileIO");
cfg.put("s3.endpoint", "https://s3.ap-southeast-2.amazonaws.com");
// ...

String catalogSql = "CREATE CATALOG lakehouse WITH (" +
    cfg.entrySet().stream()
        .map(e -> "'" + e.getKey() + "' = '" + e.getValue() + "'")
        .collect(Collectors.joining(", ")) + ")";
tEnv.executeSql(catalogSql);
```

#### Streaming read từ Iceberg

```sql
-- Hint OPTIONS bật chế độ streaming, poll mỗi 1s
SELECT ... FROM rva.bronze_raw /*+ OPTIONS('streaming'='true', 'monitor-interval'='1s') */
```

#### UDTF (User-Defined Table Function)

```java
@FunctionHint(output = @DataTypeHint("ROW<capture_ts_ms BIGINT, img_w INT, ...>"))
public class ParseDetections extends TableFunction<Row> {
    public void eval(String payload) {
        // parse JSON, flatten detections array → collect(row) cho mỗi detection
    }
}
```

#### Iceberg table với partition

```sql
CREATE TABLE IF NOT EXISTS rva.silver_detections (
    ...
) WITH (
    'format-version' = '2',
    'write.format.default' = 'parquet',
    'partitioning' = 'store_id,bucket(16, camera_id),days(capture_ts)'
);
```

#### Upsert (Gold)

```sql
CREATE TABLE IF NOT EXISTS rva.gold_track_summary (
    ...
    PRIMARY KEY (store_id, camera_id, pipeline_run_id, track_id) NOT ENFORCED
) WITH (
    'write.upsert.enabled' = 'true'
);
```

#### JSON_VALUE để extract field từ raw payload

```sql
SELECT
    JSON_VALUE(raw_payload, '$.schema_version') AS schema_version,
    JSON_VALUE(raw_payload, '$.source.camera_id') AS camera_id,
    ...
FROM pulsar_source
```

### Ưu điểm
- SQL declarative — dễ đọc, dễ giải thích trong đồ án
- Iceberg integration native (không cần custom sink)
- Schema evolution, hidden partitioning, upsert mode

### Nhược điểm
- Không có side output (invalid events không route được ra nhánh riêng)
- Custom sink khó (phải viết connector hoặc dùng DataStream bridge)
- Latency bị gated bởi checkpoint interval (60s) và Iceberg commit cycle
- Khó kiểm soát state chi tiết (chỉ qua SQL windows/joins)

---

## 3. DataStream API — Realtime Path

### Khi nào dùng

- Cần custom sink (Redis, WebSocket, custom HTTP)
- Cần side output (DLQ, late events, metrics riêng)
- Cần keyed state, timer, hoặc pattern matching (CEP)
- Cần watermark và event time xử lý thủ công
- Latency yêu cầu <5s, không phụ thuộc Iceberg commit

### Pattern từ codebase: RealtimeMetricsJob

#### ProcessFunction với side output

```java
private static final OutputTag<String> DLQ_TAG =
    new OutputTag<>("dlq-events", Types.STRING);

static class ParseValidateFunction extends ProcessFunction<String, ParsedEvent>
        implements SerializableTimestampAssigner<ParsedEvent> {

    @Override
    public void processElement(String rawJson, Context ctx, Collector<ParsedEvent> out) {
        // parse + validate
        if (invalid) {
            ctx.output(DLQ_TAG, rawJson);  // route to DLQ side output
            return;
        }
        out.collect(evt);  // main output
    }

    @Override
    public long extractTimestamp(ParsedEvent evt, long recordTimestamp) {
        return evt.captureMs;  // event time từ capture_ts
    }
}
```

#### Watermark strategy

```java
WatermarkStrategy<ParsedEvent> watermarkStrategy = WatermarkStrategy
    .<ParsedEvent>forBoundedOutOfOrderness(Duration.ofSeconds(5))  // delay 5s
    .withTimestampAssigner(parser)
    .withIdleness(Duration.ofSeconds(30));  // idle source timeout
```

#### Custom Redis sink

```java
static class RealtimeRedisSink extends RichSinkFunction<ParsedEvent> {
    private transient JedisPool pool;

    @Override
    public void open(Configuration parameters) {
        pool = new JedisPool(host, port);
    }

    @Override
    public void invoke(ParsedEvent evt, Context context) {
        try (Jedis jedis = pool.getResource()) {
            jedis.setex("stats:count:" + cameraId, 5, String.valueOf(count));
            jedis.zincrby("heatmap:live:" + cameraId, 1.0, gridX + "," + gridY);
            // ... HSET active tracks
        }
    }

    @Override
    public void close() { pool.close(); }
}
```

#### Checkpoint (nhanh hơn lakehouse)

```java
env.enableCheckpointing(10_000L, CheckpointingMode.EXACTLY_ONCE);
// 10s thay vì 60s — đủ an toàn, giảm latency
```

#### Lấy side output

```java
SingleOutputStreamOperator<ParsedEvent> mainStream = rawStream.process(parser);
DataStream<String> dlqStream = mainStream.getSideOutput(DLQ_TAG);

mainStream
    .keyBy(evt -> evt.eventId)
    .process(new DeduplicateByEventIdFunction())
    .addSink(new RealtimeRedisSink());

dlqStream.sinkTo(dlqPulsarSink);
```

### Ưu điểm
- Side output: route invalid/late events ra DLQ Pulsar topic
- Custom sink: Redis, WebSocket, HTTP — bất kỳ thứ gì
- Keyed state + timer: dedup, window, pattern matching chi tiết
- Watermark: kiểm soát event time chính xác
- Latency: không phụ thuộc Iceberg commit

### Nhược điểm
- Code dài hơn, phức tạp hơn SQL
- Phải tự quản lý connection pool, serialization
- Không có Iceberg integration native (cần bridge nếu muốn ghi Iceberg)

---

## 4. Trade-offs Summary

| Aspect | Table API / SQL | DataStream API |
|--------|----------------|----------------|
| **Code length** | Ngắn (SQL) | Dài (Java operators) |
| **Latency** | Cao hơn (checkpoint-bound) | Thấp (<5s khả thi) |
| **Iceberg integration** | Native (CREATE TABLE, INSERT) | Qua Table API bridge |
| **Side outputs** | Không hỗ trợ | Native (OutputTag) |
| **Custom sinks** | Qua SQL connector | Qua RichSinkFunction |
| **State management** | SQL windows, joins | KeyedState, ValueState, MapState, Timer |
| **Schema evolution** | Tự động (Iceberg) | Thủ công (POJO) |
| **DLQ routing** | Không (chỉ filter null) | Có (side output) |
| **Best for** | Lakehouse, ETL, analytics | Realtime serving, alerts, custom sinks |

---

## 5. Common Pitfalls

1. **UTDF throw exception** → task fail. Dùng try-catch + log + metric counter thay vì throw.
2. **Watermark không tiến** nếu source idle → dùng `withIdleness()` để tránh window không đóng.
3. **Checkpoint quá ngắn** (<5s) → overhead cao, ảnh hưởng throughput. 10s cho realtime, 30-60s cho lakehouse.
4. **Redis connection không pool** → mỗi record mở kết nối mới, rất chậm. Luôn dùng JedisPool.
5. **SimpleStringSchema cho Pulsar** → trả về `String`, không parse JSON tự động. Phải tự parse trong ProcessFunction.
6. **Side output type mismatch** → OutputTag phải khớp type với data stream. Dùng `Types.STRING` cho raw JSON, custom type cho POJO.

---

## 6. Decision Tree

```
Cần ghi Iceberg? 
  ├─ Yes → Table API / SQL
  └─ No → tiếp tục

Cần side output (DLQ, late events)?
  ├─ Yes → DataStream API
  └─ No → tiếp tục

Cần custom sink (Redis, WebSocket, HTTP)?
  ├─ Yes → DataStream API
  └─ No → tiếp tục

Cần latency <10s?
  ├─ Yes → DataStream API
  └─ No → Table API / SQL (đơn giản hơn)
```

---

## 7. References in Codebase

| Pattern | File |
|--------|------|
| Table API + Iceberg catalog | [BronzeIngestJob.java](../services/flink-jobs/java/src/main/java/org/rva/BronzeIngestJob.java) |
| UDTF flatten JSON | [ParseDetections.java](../services/flink-jobs/java/src/main/java/org/rva/silver/udf/ParseDetections.java) |
| Iceberg streaming read | [SilverJob.java](../services/flink-jobs/java/src/main/java/org/rva/silver/SilverJob.java) |
| Iceberg upsert | [GoldTrackSummaryJob.java](../services/flink-jobs/java/src/main/java/org/rva/gold/GoldTrackSummaryJob.java) |
| DataStream + ProcessFunction + keyed-state dedup + Redis/DLQ sinks | [RealtimeMetricsJob.java](../services/flink-jobs/java/src/main/java/org/rva/realtime/RealtimeMetricsJob.java) |
