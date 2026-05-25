# Pulsar Architecture — Topics, Partitions, Broker & Message Routing

> Cách Pulsar tổ chức tenant/namespace/topic/partition, cách Vision producer route message theo `partition_key`, và cách Flink consumer nhận message từ subscription độc lập.

---

## 1. Pulsar cluster — single broker (standalone mode)

```mermaid
graph TB
    subgraph Pulsar["Apache Pulsar (standalone mode)"]
        BK["pulsar-broker<br/>port: 6650 (binary)<br/>port: 8080 (admin)"]
        BK2["(standalone = 1 broker làm tất cả:<br/>broker + bookie + zookeeper)"]
    end

    subgraph Clients["Clients"]
        V1["cam_01 PulsarEmitter<br/>producer"]
        V2["cam_02 PulsarEmitter<br/>producer"]
        F1["BronzeIngestJob<br/>consumer (Table API)"]
        F2["RealtimeMetricsJob<br/>consumer (DataStream)"]
        F3["RealtimeMetricsJob<br/>producer (DLQ)"]
    end

    V1 -->|"TCP :6650<br/>produce metadata"| BK
    V2 -->|"TCP :6650<br/>produce metadata"| BK
    F1 -->|"TCP :6650<br/>consume + ack"| BK
    F2 -->|"TCP :6650<br/>consume + ack"| BK
    F3 -->|"TCP :6650<br/>produce DLQ"| BK
```

---

## 2. Tenant → Namespace → Topic → Partition hierarchy

```mermaid
graph LR
    subgraph Tenant["Tenant: retail"]
        subgraph NS_META["Namespace: retail/metadata"]
            T_EVENTS["events<br/>(partitioned, 2 partitions)"]
            T_MEDIA["media-events<br/>(partitioned, 1 partition)"]
            T_DLQ["dlq-events<br/>(partitioned, 1 partition)"]
        end
    end

    subgraph Partitions_E["events partitions"]
        P0["partition-0"]
        P1["partition-1"]
    end

    subgraph Partitions_M["media-events partitions"]
        P_M0["partition-0"]
    end

    subgraph Partitions_D["dlq-events partitions"]
        P_D0["partition-0"]
    end

    T_EVENTS --> P0
    T_EVENTS --> P1
    T_MEDIA --> P_M0
    T_DLQ --> P_D0
```

---

## 3. Message routing — partition_key quyết định partition

```mermaid
sequenceDiagram
    participant V1 as cam_01 Producer
    participant V2 as cam_02 Producer
    participant BK as Pulsar Broker
    participant P0 as events-partition-0
    participant P1 as events-partition-1

    Note over V1,BK: cam_01 gửi frame với partition_key="cam_01"

    V1->>BK: send(payload, partition_key="cam_01")
    Note over BK: hash("cam_01") % 2 = 0
    BK->>P0: append message (cam_01 frame #1)

    V1->>BK: send(payload, partition_key="cam_01")
    Note over BK: hash("cam_01") % 2 = 0 → partition 0
    BK->>P0: append message (cam_01 frame #2)

    Note over V2,BK: cam_02 gửi frame với partition_key="cam_02"

    V2->>BK: send(payload, partition_key="cam_02")
    Note over BK: hash("cam_02") % 2 = 1 → partition 1
    BK->>P1: append message (cam_02 frame #1)

    V2->>BK: send(payload, partition_key="cam_02")
    Note over BK: hash("cam_02") % 2 = 1 → partition 1
    BK->>P1: append message (cam_02 frame #2)

    Note over P0,P1: Kết quả:<br/>Partition 0: cam_01 frame #1, #2, #3... (ordering tuyệt đối)<br/>Partition 1: cam_02 frame #1, #2, #3... (ordering tuyệt đối)
```

### Công thức routing

```
partition = hash(partition_key) % num_partitions

hash("cam_01") % 2 = partition 0
hash("cam_02") % 2 = partition 1
```

Nếu không set `partition_key`:
```
round_robin:
  frame #1 → partition 0
  frame #2 → partition 1
  frame #3 → partition 0
  → ordering của camera KHÔNG được đảm bảo!
```

---

## 4. Subscription model — 2 consumer, 2 cursor độc lập

```mermaid
graph TB
    subgraph Topic["events topic"]
        P0["partition-0<br/>cam_01 frames"]
        P1["partition-1<br/>cam_02 frames"]
    end

    subgraph Sub1["Subscription: flink-bronze-java-sub"]
        C1["cursor partition-0<br/>start: earliest"]
        C2["cursor partition-1<br/>start: earliest"]
    end

    subgraph Sub2["Subscription: flink-realtime-sub"]
        C3["cursor partition-0<br/>start: latest"]
        C4["cursor partition-1<br/>start: latest"]
    end

    P0 -->|"deliver"| C1
    P0 -->|"deliver"| C3
    P1 -->|"deliver"| C2
    P1 -->|"deliver"| C4

    C1 -->|"ack"| B1["BronzeIngestJob<br/>consumer"]
    C2 -->|"ack"| B1
    C3 -->|"ack"| R1["RealtimeMetricsJob<br/>consumer"]
    C4 -->|"ack"| R1

    style Sub1 fill:#e3f2fd
    style Sub2 fill:#c8e6c9
```

### Cursor hoạt động độc lập

```
events topic:
┌──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│  E1  │  E2  │  E3  │  E4  │  E5  │  E6  │ ...  │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┘
        ▲                    ▲
        │                    │
flink-bronze-java-sub ──────┘                    │  (đọc từ earliest, đuổi dần)
flink-realtime-sub ──────────────────────────────┘  (đọc từ latest, chỉ event mới)
```

Mỗi subscription có cursor riêng, độc lập:
- Bronze đọc toàn bộ lịch sử để lưu vào Iceberg
- Realtime chỉ đọc event mới để cập nhật Redis

---

## 5. DLQ flow — invalid event được publish vào topic riêng

```mermaid
sequenceDiagram
    participant P as events topic
    participant R as RealtimeMetricsJob
    participant D as dlq-events topic (partition-0)

    P->>R: deliver: {"event_id":"", "camera_id":"cam_01", ...}

    R->>R: ParseValidateFunction<br/>validate event_id
    Note over R: event_id="" → INVALID!

    R->>R: buildDlqEnvelope(<br/>  reason="missing required field: event_id",<br/>  source_topic="persistent://retail/metadata/events",<br/>  failed_at="2026-05-17T10:30:05Z",<br/>  raw_payload="{...json gốc...}"<br/>)

    R->>D: PulsarSink.send(envelope_json)

    Note over D: DLQ message lưu lại để:<br/>- debug: tại sao event lỗi?<br/>- audit: bao nhiêu event lỗi?<br/>- replay: sửa bug xong, đọc lại xử lý
```

---

## 6. Tổng quan toàn bộ luồng message

```mermaid
flowchart TB
    subgraph Producers["Producers (4 nguồn)"]
        P_CAM01["cam_01<br/>PulsarEmitter<br/>partition_key=cam_01"]
        P_CAM02["cam_02<br/>PulsarEmitter<br/>partition_key=cam_02"]
        P_MEDIA01["cam_01<br/>media upload event<br/>(no partition key)"]
        P_MEDIA02["cam_02<br/>media upload event<br/>(no partition key)"]
    end

    subgraph PulsarTopics["Pulsar Topics"]
        direction TB
        EVENTS["events (2 partitions)"]
        MEDIA["media-events (1 partition)"]
        DLQ["dlq-events (1 partition)"]
    end

    subgraph Consumers["Consumers (3 consumer groups)"]
        C_BRONZE["BronzeIngestJob<br/>sub: flink-bronze-java-sub<br/>start: earliest<br/>→ Iceberg bronze_raw"]
        C_REALTIME["RealtimeMetricsJob<br/>sub: flink-realtime-sub<br/>start: latest<br/>→ Redis + DLQ"]
        C_DLQ["(future)<br/>DLQ consumer<br/>→ alert/monitoring"]
    end

    subgraph DLQ_Producer["DLQ Producer"]
        P_DLQ["RealtimeMetricsJob<br/>PulsarSink<br/>invalid event envelope"]
    end

    P_CAM01 -->|"hash(cam_01)%2=0"| EVENTS
    P_CAM02 -->|"hash(cam_02)%2=1"| EVENTS
    P_MEDIA01 -->|"round-robin"| MEDIA
    P_MEDIA02 -->|"round-robin"| MEDIA

    EVENTS --> C_BRONZE
    EVENTS --> C_REALTIME

    P_DLQ --> DLQ
    DLQ -.-> C_DLQ
```

---

## 7. Key decisions

| Quyết định | Lý do |
|------------|-------|
| **2 partition cho events** | 2 camera → hash(partition_key) phân phối đều, mỗi camera 1 partition, giữ ordering |
| **1 partition cho media-events** | Throughput thấp (~2 msg/s), không cần song song |
| **1 partition cho dlq-events** | Gần như 0 message, chỉ debug/audit |
| **partition_key = camera_id** | Đảm bảo frame của cùng camera luôn vào cùng partition → ordering |
| **2 subscription khác nhau** | Bronze cần toàn bộ lịch sử (earliest), Realtime chỉ cần dữ liệu mới (latest) |
| **DLQ là topic riêng** | Tách biệt invalid event khỏi pipeline chính, dễ monitor |
| **Schema registry trên events** | Phase 1 đăng ký schema contract trong Pulsar; schema validation vẫn disabled để producer raw JSON hiện tại không bị reject |

---

## 8. Scaling lên nhiều camera hơn

```text
4 camera: events -p 4, partition_key=camera_id
  cam_01 → hash % 4 = partition 0
  cam_02 → hash % 4 = partition 1
  cam_03 → hash % 4 = partition 2
  cam_04 → hash % 4 = partition 3

8 camera: events -p 8, partition_key=camera_id
  ... (tương tự, 1 camera = 1 partition)
```

Công thức: `partition_count ≥ camera_count`, set qua env `PULSAR_EVENTS_PARTITIONS`.
