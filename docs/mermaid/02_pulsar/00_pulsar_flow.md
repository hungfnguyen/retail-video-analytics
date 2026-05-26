# Pulsar Flow — Multi-Camera Vision → Flink Dual-Path

> Cách Apache Pulsar kết nối Vision module (multi-camera) với Flink processing (dual-path) trong RVA.

---

## 1. Tổng quan — Pulsar là trung tâm

```mermaid
graph TB
    subgraph Vision["Vision Service (Python multiprocessing)"]
        CAM01["CameraWorker cam_01<br/>Process"]
        CAM02["CameraWorker cam_02<br/>Process"]
        CAM01 -->|"YOLO → track → build event"| EMIT01["PulsarEmitter"]
        CAM02 -->|"YOLO → track → build event"| EMIT02["PulsarEmitter"]
    end

    subgraph Pulsar["Apache Pulsar (retail/metadata)"]
        EVENTS["events<br/>persistent://retail/metadata/events<br/>2 partitions"]
        MEDIA["media-events<br/>persistent://retail/metadata/media-events<br/>1 partition"]
        DLQ["dlq-events<br/>persistent://retail/metadata/dlq-events<br/>1 partition"]
    end

    subgraph Flink["Apache Flink (4 jobs)"]
        BRONZE["BronzeIngestJob<br/>Table API<br/>sub: flink-bronze-java-sub"]
        REALTIME["RealtimeMetricsJob<br/>DataStream API<br/>sub: flink-realtime-sub"]
        SILVER["SilverJob<br/>Table API<br/>source: Iceberg"]
        GOLD["GoldTrackSummaryJob<br/>Table API<br/>source: Iceberg"]
    end

    EMIT01 -->|"metadata JSON<br/>(có event_id)"| EVENTS
    EMIT02 -->|"metadata JSON<br/>(có event_id)"| EVENTS
    EMIT01 -.->|"sampled JPEG / alert MP4<br/>media artifact events"| MEDIA
    EMIT02 -.->|"sampled JPEG / alert MP4<br/>media artifact events"| MEDIA

    EVENTS --> BRONZE
    EVENTS --> REALTIME
    REALTIME -->|"invalid events<br/>PulsarSink"| DLQ
```

---

## 2. Vision → Pulsar: 1 camera = 1 producer

```mermaid
sequenceDiagram
    participant Main as CameraManager (main.py)
    participant W1 as Worker Process cam_01
    participant W2 as Worker Process cam_02
    participant P as Pulsar Broker

    Main->>W1: Process(target=run_worker, args=(cam_01))
    Main->>W2: Process(target=run_worker, args=(cam_02))

    Note over W1,P: Mỗi worker tạo PulsarClient riêng<br/>(không share được qua multiprocessing)

    W1->>P: PulsarClient(listener_name='external')
    W1->>P: create_producer(topic=events)
    W1->>P: create_producer(topic=media-events) [optional]

    W2->>P: PulsarClient(listener_name='external')
    W2->>P: create_producer(topic=events)
    W2->>P: create_producer(topic=media-events) [optional]

    loop Frame loop per camera
        W1->>W1: read frame → detect → track → build event_id
        W1->>P: producer.send(DetectionFrameEvent JSON)
        W1-->>P: retry 3x exponential backoff nếu fail
        W2->>W2: read frame → detect → track → build event_id
        W2->>P: producer.send(DetectionFrameEvent JSON)
        W2-->>P: retry 3x exponential backoff nếu fail
    end

    Main->>W1: SIGTERM → process.terminate()
    Main->>W2: SIGTERM → process.terminate()
    W1->>P: producer.close() → client.close()
    W2->>P: producer.close() → client.close()
```

---

## 3. Pulsar internals: topics, subscriptions, message flow

```mermaid
graph LR
    subgraph Tenant["Tenant: retail"]
        subgraph NS_META["Namespace: retail/metadata"]
            T_EVENTS["events<br/>(partitioned, 2 parts)"]
            T_MEDIA["media-events<br/>(partitioned, 1 part)"]
            T_DLQ["dlq-events<br/>(partitioned, 1 part)"]
        end
    end

    subgraph Producers["Producers"]
        P1["cam_01 PulsarEmitter"]
        P2["cam_02 PulsarEmitter"]
        P3["RealtimeMetricsJob<br/>(DLQ PulsarSink)"]
    end

    subgraph Subscriptions["Subscriptions (independent cursors)"]
        SUB1["flink-bronze-java-sub<br/>start: earliest"]
        SUB2["flink-realtime-sub<br/>start: latest"]
    end

    subgraph Schema["Pulsar Schema Registry"]
        SCH["metadata-json-schema.json<br/>registered contract<br/>validation disabled in phase 1"]
    end

    P1 -->|"frame metadata + event_id"| T_EVENTS
    P2 -->|"frame metadata + event_id"| T_EVENTS
    P1 -->|"sampled frame / alert clip"| T_MEDIA
    P2 -->|"sampled frame / alert clip"| T_MEDIA
    P3 -->|"invalid event envelope"| T_DLQ

    T_EVENTS --> SUB1
    T_EVENTS --> SUB2
    T_EVENTS -.-> SCH
```

### Cursor hoạt động độc lập

```
                    Pulsar Topic events
                    ┌────┬────┬────┬────┬────┬────┐
                    │ E1 │ E2 │ E3 │ E4 │ E5 │ E6 │  ...
                    └────┴────┴────┴────┴────┴────┘
                              ▲              ▲
                              │              │
    flink-bronze-java-sub ────┘              │  (đọc từ earliest, đuổi dần)
    flink-realtime-sub ──────────────────────┘  (đọc từ latest, chỉ event mới)
```

Mỗi subscription có **cursor riêng** → Bronze đọc toàn bộ lịch sử, Realtime chỉ đọc event mới.

---

## 4. Pulsar → Flink: 2 source, 2 subscription

```mermaid
flowchart TB
    TOPIC["persistent://retail/metadata/events"]

    TOPIC --> SUB1["Subscription: flink-bronze-java-sub<br/>(start: earliest, cursor riêng)"]
    TOPIC --> SUB2["Subscription: flink-realtime-sub<br/>(start: latest, cursor riêng)"]

    SUB1 --> BR_FMT["Table API SQL connector<br/>'format'='raw'<br/>raw_payload STRING"]
    BR_FMT --> BR_INSERT["INSERT INTO bronze_raw<br/>JSON_VALUE(raw_payload, '$.event_id')<br/>JSON_VALUE(raw_payload, '$.source.camera_id')<br/>..."]
    BR_INSERT --> ICE1["Iceberg bronze_raw<br/>(raw + extracted fields)"]

    SUB2 --> RT_SRC["DataStream PulsarSource<br/>SimpleStringSchema()<br/>raw json string"]
    RT_SRC --> RT_PARSE["ParseValidateFunction<br/>ProcessFunction"]
    RT_PARSE --> RT_VALID["valid event"]
    RT_PARSE --> RT_INVALID["invalid event → OutputTag(DLQ)"]
    RT_VALID --> RT_DEDUP["DeduplicateByEventIdFunction<br/>ValueState TTL 10min"]
    RT_DEDUP --> RT_REDIS["RealtimeRedisSink<br/>SET count, ZINCRBY heatmap, HSET track"]
    RT_INVALID --> RT_DLQ["buildDlqEnvelope()<br/>{reason, source_topic, failed_at, raw_payload}"]
    RT_DLQ --> DLQ_SINK["PulsarSink"]
    DLQ_SINK --> DLQ_TOPIC["persistent://retail/metadata/dlq-events"]

    style BRONZE fill:#e1f5fe
    style RT_REDIS fill:#c8e6c9
    style DLQ_SINK fill:#ffcdd2
```

---

## 5. Message lifecycle — từ Vision đến Flink

```mermaid
sequenceDiagram
    participant V as Vision Worker (cam_01)
    participant P as Pulsar Broker
    participant B as BronzeIngestJob (Flink)
    participant R as RealtimeMetricsJob (Flink)
    participant RD as Redis
    participant DLQ as DLQ Topic

    V->>V: frame_index=42, capture_ts=...
    V->>V: event_id = sha256("cam_01|ts|42")[:16]
    V->>V: DetectionFrameEvent(event_id="a1b2...")
    V->>P: producer.send(payload) [attempt 1/3]

    alt send fail
        V->>V: sleep 0.5s → retry
        V->>P: producer.send(payload) [attempt 2/3]
    end

    P-->>B: deliver (sub: flink-bronze-java-sub)
    P-->>R: deliver (sub: flink-realtime-sub)

    par Lakehouse path
        B->>B: JSON_VALUE(payload, '$.event_id')
        B->>B: INSERT INTO bronze_raw
    end

    par Realtime path
        R->>R: parse JSON → validate fields
        alt valid
            R->>R: keyBy(eventId) → dedup check
            R->>RD: SET stats:count:cam_01 15 EX 5
            R->>RD: ZINCRBY heatmap:live:cam_01 1 "32,18"
            R->>RD: HSET track:active:cam_01:7 ...
        else invalid (missing event_id, bad camera_id...)
            R->>R: buildDlqEnvelope(reason, raw_payload)
            R->>DLQ: PulsarSink.send(envelope)
        end
    end
```

---

## 6. DLQ envelope format

```json
{
    "schema_version": "1.0",
    "event_type": "invalid_detection_event",
    "reason": "missing required field: event_id",
    "source_topic": "persistent://retail/metadata/events",
    "failed_at": "2026-05-17T10:30:05.123Z",
    "raw_payload": "{\"schema_version\":\"1.0\",\"pipeline_run_id\":\"abc123\",...}"
}
```

| Field | Ý nghĩa |
|-------|--------|
| `reason` | Tại sao event bị reject |
| `source_topic` | Topic gốc của event |
| `failed_at` | Thời điểm Flink reject |
| `raw_payload` | JSON gốc (để debug/replay) |

---

## 7. Key takeaways

| Nguyên tắc | Chi tiết |
|------------|---------|
| **1 camera = 1 PulsarClient** | Multiprocessing không share được Pulsar client |
| **Tất cả camera → 1 topic** | Flink keyed by `camera_id` để tách luồng |
| **2 subscription = 2 cursor độc lập** | Bronze đọc từ `earliest`, Realtime từ `latest` |
| **Lakehouse path = Table API** | SQL connector, không code Java Pulsar |
| **Realtime path = DataStream API** | PulsarSource builder + PulsarSink cho DLQ |
| **DLQ = PulsarSink thật** | Không chỉ log, publish vào `dlq-events` topic |
| **event_id = SHA256 deterministic** | Sinh ở Vision, dùng cho dedup ở Flink |
