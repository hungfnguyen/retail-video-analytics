# Streaming Pipeline

## Topology

```text
                       Pulsar events
                            |
          +-----------------+-----------------+
          |                                   |
          v                                   v
  Lakehouse path                       Realtime path
  Table API / SQL                      DataStream API
          |                                   |
          v                                   v
  Iceberg tables                       Redis + DLQ
```

## Flink Jobs

| Job | API | Input | Output | Role |
|---|---|---|---|---|
| `BronzeIngestJob` | Table API | Pulsar raw JSON | `lakehouse.rva.bronze_raw` | Raw audit trail |
| `SilverJob` | Table API | `bronze_raw` streaming read | `lakehouse.rva.silver_detections` | Flatten and clean detections |
| `GoldTrackSummaryJob` | Table API | `silver_detections` streaming read | `lakehouse.rva.gold_track_summary` | Track-level aggregate |
| `RealtimeMetricsJob` | DataStream API | Pulsar raw JSON | Redis + DLQ topic | Low-latency dashboard state |

## Lakehouse Path

```text
Pulsar -> BronzeIngestJob -> bronze_raw
bronze_raw -> SilverJob -> silver_detections
silver_detections -> GoldTrackSummaryJob -> gold_track_summary
```

Bronze keeps the raw payload. Silver uses a UDTF to parse detections, validates fields, filters confidence, and deduplicates detection rows. Gold aggregates each track into enter/exit/duration/frame-count summary rows.

## Realtime Path

```text
Pulsar -> ParseValidateFunction -> DeduplicateByEventIdFunction -> Redis
                                `-> invalid events -> DLQ Pulsar topic
```

Redis output:

```text
stats:count:{camera_id}
live:frame:{camera_id}
heatmap:live:{camera_id}
track:active:{camera_id}:{track_id}
```

## Validation

Realtime validation rejects events with missing or invalid:

- `event_id`
- `source.camera_id`
- `source.store_id`
- `capture_ts`
- `image_size`

Invalid events are wrapped with a reason and published to `persistent://retail/metadata/dlq-events`.

## Deduplication

| Path | Key | Mechanism |
|---|---|---|
| Realtime | `event_id` | Flink keyed state with TTL |
| Silver | `event_id + detection key` | SQL `ROW_NUMBER()` |

## Checkpointing

| Job | Current interval |
|---|---:|
| Bronze | 60 seconds |
| Realtime | 10 seconds |

Iceberg visibility depends on checkpoint commits. Redis updates are visible immediately after the sink writes.

## Operational Verification

```bash
curl -s http://localhost:8081/jobs/overview

docker exec redis redis-cli GET stats:count:cam_01
docker exec redis redis-cli ZREVRANGE heatmap:live:cam_01 0 10 WITHSCORES

docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.bronze_raw"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.silver_detections"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.gold_track_summary"
```
