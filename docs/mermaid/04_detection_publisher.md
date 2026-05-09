# 04 — DetectionPublisher: Publish lên Pulsar

## Publish flow với retry

```mermaid
flowchart TB
    subgraph Publisher["DetectionPublisher"]
        Event["DetectionFrameEvent\n(từ pipeline)"]
        Serialize["json.dumps(event)"]
        Send["producer.send_async(payload)"]
        Success{success?}
        Done["✅ Done\n(frame_index % 30 == 0: log info)"]

        Event --> Serialize --> Send --> Success
        Success -->|"OK"| Done
        Success -->|"fail"| Retry["Retry loop (max 3 attempts)\n+ exponential backoff"]
        Retry -->|"attempt < 3"| Send
        Retry -->|"exhausted"| Fail["❌ Log ERROR\n+ emit metric: failed_publish++"]

        Done --> Next["Tiếp tục frame tiếp theo\n(không block pipeline)"]
        Fail --> Next
    end

    style Retry fill:#f39c12,color:#000
    style Fail fill:#e74c3c,color:#fff
    style Done fill:#27ae60,color:#fff
```

## Retry backoff strategy

```mermaid
sequenceDiagram
    participant P as DetectionPublisher
    participant Prod as Pulsar Producer
    participant Broker as Pulsar Broker
    participant M as Metrics

    Note over P: gửi frame N

    P->>Prod: producer.send(payload)
    Prod-->>P: ❌ Exception (timeout / connection lost)

    Note over P: attempt=1, backoff=0.5s
    P->>P: sleep(0.5s)
    P->>Prod: producer.send(payload)
    Prod-->>P: ❌ Exception

    Note over P: attempt=2, backoff=1.0s
    P->>P: sleep(1.0s)
    P->>Prod: producer.send(payload)
    Prod-->>P: ❌ Exception

    Note over P: attempt=3, backoff=2.0s
    P->>P: sleep(2.0s)
    P->>Prod: producer.send(payload)
    Prod-->>P: ❌ Exception

    Note over P: exhausted 3 retries
    P->>M: failed_publish_total++
    Note over P: ❌ LOG: "Failed to send frame N after 3 attempts"
    Note over P: tiếp tục frame N+1
```

## Các sink output — non-blocking pattern

```mermaid
flowchart TB
    Build["build DetectionFrameEvent"] --> Split{Routing}

    subgraph Sinks["Output Sinks (all async)"]
        direction TB
        PulsarSink["PulsarEmitter\n├── async send\n├── retry 3x\n└── buffer: bounded memory"]
        FrameSink["FrameSampler\n├── save interval: 1 fps\n├── jpg quality: 80-85\n└── ThreadPoolExecutor upload"]
        TrackSink["TrackLifecycleManager\n├── track_start\n├── position_sample (1s interval)\n└── track_end (timeout 30s)"]
        MetricSink["MetricsEmitter\n├── fps\n├── detection_count\n└── publish_latency"]
    end

    Split --> PulsarSink
    Split --> FrameSink
    Split --> TrackSink
    Split --> MetricSink

    PulsarSink --> Pulsar["Pulsar"]
    FrameSink --> S3["S3/MinIO"]
    TrackSink --> PG["PostgreSQL"]
    MetricSink --> Prom["Prometheus"]

    style Sinks fill:#0d1b2a,stroke:#27ae60,color:#fff
```

> **Nguyên tắc:** Không sink nào được block inference loop. Nếu 1 sink chậm/lỗi, các sink khác vẫn hoạt động. Pipeline chính luôn tiếp tục xử lý frame tiếp theo.

## Buffer bounded memory khi Pulsar unavailable

```mermaid
flowchart LR
    Normal["Normal:\npublish → Pulsar ✅"] -->|"Pulsar down"| Buffer["Buffer mode:\nbounded queue (max N events)"]
    Buffer -->|"queue < N"| Enqueue["enqueue(event)\n→ tiếp tục pipeline"]
    Buffer -->|"queue == N (full)"| DropNew["drop event mới nhất\n→ drop_count++\n→ tiếp tục pipeline"]
    Buffer -->|"Pulsar back"| Drain["drain buffer → Pulsar\n→ resume normal mode"]

    style DropNew fill:#e74c3c,color:#fff
    style Drain fill:#27ae60,color:#fff
```

| Setting | Giá trị | Ghi chú |
|--------|--------|--------|
| `max_buffer_events` | 100 | Giới hạn memory |
| `drain_batch_size` | 10 | Gửi batch khi Pulsar trở lại |
| `drop_policy` | drop_newest | Real-time: frame mới quan trọng hơn cũ |
