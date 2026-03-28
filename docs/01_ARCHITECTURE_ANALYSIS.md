# System Architecture Overview

## Overview

Retail Video Analytics (RVA) is a production-grade streaming pipeline for real-time crowd detection and density analysis in retail stores. This document describes the system architecture, data flow, and design rationale.

---

## 1. System Architecture

```
┌─────────────────┐
│  Camera/Video   │
│  YOLO11+BoTSORT │
└────────┬────────┘
         │ JSON detections
         ▼
┌─────────────────┐
│  Apache Pulsar  │
│  Message Queue  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Apache Flink   │
│  Bronze→Silver  │
│  →Gold Jobs     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Apache Iceberg  │
│ + GCS Storage │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│     Trino       │
│  Query Engine   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Grafana      │
│   Dashboards    │
└─────────────────┘
```

### Technology Stack

| Layer | Technology | Version |
|-------|------------|---------|
| Vision | YOLO11 + BoTSORT | - |
| Message Queue | Apache Pulsar | 3.3.2 |
| Stream Processing | Apache Flink | 1.18 |
| Storage | Apache Iceberg + GCS | - |
| Query Engine | Trino | 418 |
| Visualization | Grafana + Streamlit | 11.3 / 1.30+ |

---

## 2. Streaming Pipeline

The pipeline follows the **Medallion Lakehouse** pattern used by Netflix, DoorDash, and Databricks:

```
Vision AI → Pulsar → Flink → Iceberg → Trino → Grafana
```

### What works well

1. **Streaming Pipeline Pattern**: Pulsar → Flink → Iceberg — industry-standard architecture
2. **Medallion Architecture**: Bronze → Silver → Gold — correct Databricks lakehouse pattern
3. **Lakehouse Format**: Iceberg — used by Apple, Netflix, Airbnb
4. **Query Engine**: Trino — suited for interactive analytics queries

---

## 3. Medallion Lakehouse Latency

The Slow Path (Medallion Lakehouse) has **90-120 seconds end-to-end latency**. This is by design and expected.

```
Medallion Latency Breakdown:
- Flink checkpoint interval: 30-60 seconds (default)
- Bronze: 30-60 seconds (Iceberg only commits at checkpoint)
- Silver: +30-60 seconds (separate job, separate checkpoint)
- Gold: +30-60 seconds (aggregation, separate checkpoint)
- Trino snapshot scan: +2-5 seconds
- Total worst case: 90-180 seconds

Reason: Flink Iceberg Sink only commits data at each checkpoint,
not per record. This is Iceberg's ACID transaction design —
correct behavior, but not suitable for real-time alerting.
```

**This is why the system uses Dual-Path Architecture:**
- **Fast Path**: Flink CEP → Redis → WebSocket (< 1 second) — for alerting
- **Slow Path**: Flink Batch → Iceberg → Trino (90-120 seconds) — for analytics

---

## 4. Dual-Path Architecture

```
                          ┌─────────────────────────────────────┐
                          │           EDGE LAYER                │
                          │  ┌─────────────────────────────┐    │
                          │  │   Camera 1..N (RTSP)        │    │
                          │  └──────────────┬──────────────┘    │
                          │                 │                   │
                          │  ┌──────────────▼──────────────┐    │
                          │  │   YOLO11 + BoTSORT          │    │
                          │  │   (Detection + Tracking)    │    │
                          │  └──────────────┬──────────────┘    │
                          │                 │                   │
                          │         JSON + Frames               │
                          └─────────────────┼───────────────────┘
                                            │
                ┌───────────────────────────┼───────────────────────────┐
                │                           │                           │
                ▼                           ▼                           ▼
      ┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
      │  Apache Pulsar  │         │   GCS (S3)    │         │   PostgreSQL    │
      │  (Metadata)     │         │   (Frames)      │         │   (Events)      │
      └────────┬────────┘         └─────────────────┘         └─────────────────┘
               │
   ┌───────────┴───────────┐
   │                       │
   ▼                       ▼
FAST PATH              SLOW PATH
Flink CEP              Flink Batch
(< 1 sec)              (90-120 sec)
   │                       │
   ▼                       ▼
Redis                  Iceberg
(heatmap, alerts)      (B→S→G)
   │                       │
   ▼                       ▼
WebSocket              Trino
   │                       │
   └──────────┬────────────┘
              ▼
        Streamlit + Grafana
```

---

## 5. Production Reference Architectures

### Netflix Real-Time Graph

```
User Events → Kafka → Flink Jobs → Graph DB
                 ↓
              Storage (S3/Cassandra)
```

Key patterns: 1:1 mapping topic → Flink job, separate topics per event type, checkpointed state management.

### DoorDash Event Processing

```
Services → Kafka → Flink (DataStream/SQL) → Multiple Sinks
                                              ├── Redis (real-time)
                                              ├── Snowflake (analytics)
                                              └── ElasticSearch (search)
```

Key patterns: Flink job per event type, multiple sinks for different use cases, SQL abstraction for non-developers.

### AWS Retail Video Analytics

```
Cameras → Edge Processing → Kinesis → Lambda/Flink → S3 + DynamoDB
              (YOLO)                                      ↓
                                                      QuickSight
```

Key patterns: Edge GPU (Jetson) with TensorRT, separate storage for media vs metadata, auto-scaling for video processing.

---

## 6. System Components

| Component | Role | Latency |
|-----------|------|---------|
| YOLO11 + BoTSORT | Detection + tracking at edge | 50ms/frame |
| Apache Pulsar | Metadata stream (30 FPS) | 10ms publish |
| GCS | Keyframe storage (1 frame/sec) | < 100ms |
| PostgreSQL | Track events (start/end/sample) | 5ms write |
| Flink CEP | Density alerting | < 100ms |
| Redis | Live heatmap + pub/sub | < 5ms |
| Flink Batch | Medallion ETL | 30-60s/job |
| Iceberg | Lakehouse storage | Checkpoint-bound |
| Trino | Analytics SQL | 2-5s/query |
| Streamlit | Primary dashboard | 500ms refresh |
| Grafana | Historical analytics | 30s refresh |

---

## Related Documents

- [02_ARCHITECTURE_IMPROVED.md](./02_ARCHITECTURE_IMPROVED.md) - Dual-Path architecture details
- [03_DATABASE_SCHEMA.md](./03_DATABASE_SCHEMA.md) - Database schema
- [04_VISUALIZATION_REQUIREMENTS.md](./04_VISUALIZATION_REQUIREMENTS.md) - Visualization requirements
- [05_ACTION_PLAN.md](./05_ACTION_PLAN.md) - Implementation guide
- [06_TECH_COMPARISON.md](./06_TECH_COMPARISON.md) - Technology decisions
