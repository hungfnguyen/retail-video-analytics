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
| `SilverJob` | Table API | `bronze_raw` streaming read | `lakehouse.rva.silver_detections_v2` | Flatten, clean, and enrich detections |
| `GoldTrackSummaryJob` | Table API | `silver_detections_v2` streaming read | `lakehouse.rva.gold_track_summary_v2` | Global-track lifecycle aggregate |
| `QueueAnalyticsJob` | Table API | `silver_detections_v2` streaming read | `lakehouse.rva.gold_queue_sessions_v2` | Queue session facts |
| `GoldAlertsJob` | Table API | Pulsar `media-events` | `lakehouse.rva.gold_alerts` | Clip-backed alert incidents |
| `GoldDashboardAggregateJob` | Table API | `silver_detections_v2`, `gold_track_summary_v2` streaming reads | `gold_camera_hourly_metrics`, `gold_camera_daily_metrics`, `gold_camera_daily_dwell`, `gold_alert_events` | Compact dashboard Gold facts |
| `RealtimeMetricsJob` | DataStream API | Pulsar raw JSON | Redis + DLQ topic | Low-latency dashboard state |

## Lakehouse Path

```text
Pulsar -> BronzeIngestJob -> bronze_raw
bronze_raw -> SilverJob -> silver_detections_v2
silver_detections_v2 -> GoldTrackSummaryJob -> gold_track_summary_v2
silver_detections_v2 -> QueueAnalyticsJob -> gold_queue_sessions_v2
media-events -> GoldAlertsJob -> gold_alerts
silver_detections_v2 + gold_track_summary_v2 -> GoldDashboardAggregateJob -> dashboard Gold aggregate tables
```

Bronze keeps the raw payload. Silver v2 uses a UDTF to parse detections,
validates fields, filters confidence, and keeps global track, zone, queue, and
anchor metadata. Gold aggregates global tracks, queue sessions, dashboard facts,
and clip-backed alerts. Gold serving tables in `lakehouse.rva_gold_serving`
provide query-ready data for analytics endpoints.

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
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.silver_detections_v2"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.gold_track_summary_v2"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.gold_queue_sessions_v2"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.gold_camera_daily_metrics"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.gold_camera_hourly_metrics"
docker exec trino trino --execute "SELECT COUNT(*) FROM lakehouse.rva.gold_camera_daily_dwell"
docker exec trino trino --execute "SHOW TABLES FROM lakehouse.rva_gold_serving"
```
