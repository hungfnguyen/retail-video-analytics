# Technology Decisions

## Overview

This document covers the technology choices for each system component, including decision rationale and trade-offs.

---

## 1. Message Queue: Pulsar vs Kafka

### Comparison

| Feature | Apache Pulsar | Apache Kafka |
|---------|--------------|--------------|
| **Architecture** | Multi-layer (broker + bookie) | Single-layer |
| **Storage** | Apache BookKeeper | Local disk |
| **Multi-tenancy** | Native support | Requires setup |
| **Geo-replication** | Built-in | MirrorMaker required |
| **Message TTL** | Per-topic configurable | Requires config |
| **Delayed delivery** | Native support | Not supported |
| **Schema Registry** | Built-in | Separate service |
| **Protocol Support** | Pulsar, Kafka, AMQP | Kafka only |
| **Operational Complexity** | Higher | Lower |
| **Community Size** | Smaller | Larger |
| **Cloud Offerings** | StreamNative | Confluent, AWS MSK |

### Decision: **Apache Pulsar**

**Reasons:**
1. Already in use — no migration needed
2. Built-in schema registry well-suited for video metadata
3. Multi-tenancy supports multi-store deployment
4. Delayed delivery useful for retry logic

**Trade-offs:**
- Higher operational complexity than Kafka
- Smaller community, less documentation

---

## 2. Stream Processing: Flink vs Spark Streaming vs Kafka Streams

### Comparison

| Feature | Apache Flink | Spark Streaming | Kafka Streams |
|---------|--------------|-----------------|---------------|
| **Processing Model** | True streaming | Micro-batch | True streaming |
| **Latency** | Sub-second | Seconds | Sub-second |
| **State Management** | RocksDB, memory | External | RocksDB |
| **Exactly-once** | Native | With Kafka | With Kafka |
| **SQL Support** | Flink SQL | Spark SQL | KSQL |
| **CEP (Complex Event)** | Native FlinkCEP | Limited | Limited |
| **Windowing** | Advanced | Basic | Basic |
| **Checkpointing** | Asynchronous | Synchronous | Changelog |
| **Resource Usage** | Moderate | High | Low |
| **Deployment** | Standalone, YARN, K8s | YARN, K8s, Standalone | Library (embedded) |

### Decision: **Apache Flink**

**Reasons:**
1. True streaming with sub-second latency for alerting
2. FlinkCEP is the right tool for crowd detection patterns
3. Advanced windowing for time-based aggregations
4. Flink SQL enables non-developer access
5. Already in use

**Trade-offs:**
- Steeper learning curve
- Requires dedicated cluster

---

## 3. Real-time Database: Redis vs Druid vs ClickHouse

### Comparison

| Feature | Redis | Apache Druid | ClickHouse |
|---------|-------|--------------|------------|
| **Primary Use** | Cache, State | OLAP, Time-series | OLAP, Analytics |
| **Latency** | Sub-ms | Sub-second | Sub-second |
| **Data Model** | Key-Value | Columnar | Columnar |
| **Query Language** | Commands | SQL-like | SQL |
| **Aggregations** | Limited | Excellent | Excellent |
| **Time-series** | Limited | Native | Good |
| **Pub/Sub** | Native | No | No |
| **Complexity** | Low | High | Medium |
| **Memory Usage** | All in RAM | RAM + Disk | RAM + Disk |

### Decision: **Redis** (primary) + **Druid** (optional/future)

**Redis for:**
- Real-time state (live heatmap, active tracks)
- Pub/Sub for WebSocket
- Caching
- Alert queue

**Druid (optional, future):**
- Real-time OLAP queries
- Sub-second analytics
- Time-series aggregations

**Reasons for Redis:**
1. Sub-millisecond latency
2. Native Pub/Sub for WebSocket
3. Simple operations, low complexity
4. Sufficient for current scale (< 100 cameras)

---

## 4. Storage: Iceberg vs Delta Lake vs Hudi

### Comparison

| Feature | Apache Iceberg | Delta Lake | Apache Hudi |
|---------|---------------|------------|-------------|
| **Created by** | Netflix | Databricks | Uber |
| **Open Source** | Fully open | Open (core) | Fully open |
| **Time Travel** | Yes | Yes | Yes |
| **Schema Evolution** | Excellent | Good | Good |
| **Partition Evolution** | Yes | No | No |
| **Hidden Partitioning** | Yes | No | No |
| **Engine Support** | Spark, Flink, Trino, Presto | Spark, Flink (limited) | Spark, Flink |
| **File Formats** | Parquet, ORC, Avro | Parquet | Parquet |
| **Compaction** | Built-in | Delta optimize | Built-in |

### Decision: **Apache Iceberg**

**Reasons:**
1. Already in use
2. Excellent Flink integration
3. Native Trino support
4. Hidden partitioning reduces complexity
5. Schema evolution supports video metadata changes

---

## 5. Query Engine: Trino vs Presto vs Spark SQL

### Comparison

| Feature | Trino | Presto | Spark SQL |
|---------|-------|--------|-----------|
| **Origin** | Presto fork | Facebook | Apache |
| **Architecture** | Massively parallel | Massively parallel | MapReduce-style |
| **Latency** | Sub-second | Sub-second | Seconds to minutes |
| **Memory Model** | In-memory | In-memory | Disk + Memory |
| **Connectors** | 100+ | 50+ | 50+ |
| **Iceberg Support** | Excellent | Good | Good |
| **Cost-based Optimizer** | Yes | Yes | Yes |
| **Fault Tolerance** | Limited | Limited | Excellent |

### Decision: **Trino**

**Reasons:**
1. Already in use
2. Excellent Iceberg integration
3. Sub-second queries for dashboards
4. Active community and development

---

## 6. Visualization: Grafana vs Streamlit vs Superset

### Comparison

| Feature | Grafana | Streamlit | Apache Superset |
|---------|---------|-----------|-----------------|
| **Primary Use** | Monitoring, Time-series | Custom apps, Data science | BI, Dashboards |
| **Video Support** | No | Yes | No |
| **Real-time** | Polling | WebSocket | Polling |
| **Custom UI** | Limited | Full Python | Limited |
| **Heatmap Overlay** | Limited | Full control | Limited |
| **SQL Support** | Yes | Manual | Yes |
| **Setup Time** | Fast | Medium | Medium |
| **Learning Curve** | Low | Medium | Medium |
| **Alerting** | Built-in | Manual | Limited |

### Decision: **Both — Grafana + Streamlit**

**Grafana for:**
- Time-series monitoring (traffic trends)
- System health dashboards
- Built-in alerting
- Store Manager daily view

**Streamlit for:**
- Live video with overlays
- Real-time heatmap on video frames
- Event investigation
- Track replay
- Custom interactive features

**Reasons for using both:**
1. Each tool has distinct strengths
2. Different user personas need different tools
3. Grafana is already in the stack
4. Streamlit is easy to develop for video features

---

## 7. Metadata Database: PostgreSQL vs MongoDB vs MySQL

### Comparison

| Feature | PostgreSQL | MongoDB | MySQL |
|---------|------------|---------|-------|
| **Data Model** | Relational | Document | Relational |
| **JSON Support** | JSONB (excellent) | Native | JSON (basic) |
| **Full-text Search** | Built-in | Built-in | Full-text index |
| **Geospatial** | PostGIS | Native | Limited |
| **Partitioning** | Native | Sharding | Native |
| **Replication** | Streaming | Replica sets | Master-slave |
| **ACID** | Full | Tunable | Full |
| **Extensions** | Rich ecosystem | Plugins | Limited |

### Decision: **PostgreSQL**

**Reasons:**
1. JSONB for flexible metadata (bbox, path coordinates)
2. Excellent indexing for time-range queries
3. Native partitioning for large event tables
4. Rich extension ecosystem
5. Better suited for analytics queries

---

## 8. Object Storage: GCS vs AWS S3 vs MinIO

### Comparison

| Feature | Google Cloud Storage | AWS S3 | MinIO |
|---------|---------------------|--------|-------|
| **Deployment** | Managed cloud | Managed cloud | Self-hosted |
| **Performance** | High | High | High |
| **Operational** | Fully managed | Fully managed | Self-managed |
| **Cost** | Pay-per-use | Pay-per-use | Infrastructure only |
| **Lifecycle Policies** | Built-in | Built-in | Built-in |
| **Versioning** | Yes | Yes | Yes |
| **Global CDN** | Cloud CDN | CloudFront | Manual |
| **IAM Integration** | GCP IAM | AWS IAM | Custom |
| **Signed URLs** | Yes | Yes | Yes |

### Decision: **Google Cloud Storage (GCS)**

**Reasons:**
1. Fully managed — no infrastructure to operate
2. Native GCP IAM for access control
3. Built-in lifecycle policies for 7-day frame retention
4. Signed URLs for secure frame access from Streamlit
5. Seamless integration with other GCP services (Dataflow, BigQuery)
6. High durability (99.999999999%) with no operational overhead

---

## 9. WebSocket Server: FastAPI vs Socket.io vs Native

### Comparison

| Feature | FastAPI + Starlette | Socket.io | Native WebSocket |
|---------|---------------------|-----------|------------------|
| **Language** | Python | Node.js / Python | Any |
| **Complexity** | Low | Medium | Low |
| **Rooms/Namespaces** | Manual | Built-in | Manual |
| **Fallback** | No | Yes (polling) | No |
| **Binary Support** | Yes | Yes | Yes |
| **Redis Adapter** | Manual | Built-in | Manual |

### Decision: **FastAPI + Starlette**

**Reasons:**
1. Consistent with the Python ecosystem
2. Native async
3. Simple integration with Redis pub/sub
4. Good documentation

---

## 10. Summary Decision Matrix

| Component | Decision | Confidence | Alternatives |
|-----------|----------|------------|--------------|
| Message Queue | Pulsar | High | Kafka |
| Stream Processing | Flink | High | Spark Streaming |
| Real-time State | Redis | High | Druid, ClickHouse |
| Lakehouse Format | Iceberg | High | Delta Lake |
| Query Engine | Trino | High | Presto |
| Monitoring Dashboard | Grafana | High | - |
| Custom Dashboard | Streamlit | High | React, Superset |
| Metadata DB | PostgreSQL | High | MongoDB |
| Object Storage | GCS | High | AWS S3 |
| WebSocket | FastAPI | Medium | Socket.io |

---

## 11. Scaling Considerations

### Beyond 100 Cameras

| Component | Current | Scale-up Option |
|-----------|---------|-----------------|
| Redis | Single node | Redis Cluster |
| PostgreSQL | Single instance | Read replicas + partitioning |
| GCS | Single bucket | Multi-region buckets |
| Flink | Single job | Multiple jobs, higher parallelism |

### ML Integration (Future)

| Feature | Add-on |
|---------|--------|
| Face recognition | OpenCV + face_recognition |
| Behavior analysis | TensorFlow/PyTorch model |
| Anomaly detection | Flink ML or external service |

### Multi-Region (Future)

| Component | Strategy |
|-----------|----------|
| Pulsar | Geo-replication |
| GCS | Multi-region bucket |
| PostgreSQL | Streaming replication |
| Flink | Regional deployments |

---

## Related Documents

- [02_ARCHITECTURE_IMPROVED.md](./02_ARCHITECTURE_IMPROVED.md) - How components connect
- [05_ACTION_PLAN.md](./05_ACTION_PLAN.md) - Implementation details
