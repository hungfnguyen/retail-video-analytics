# Operational Storage

This project separates low-latency serving state from historical analytical storage.

## Storage Roles

| Storage | Role | Retention |
|---|---|---|
| Redis | Realtime dashboard state | Short TTL |
| Local live frame directory | Latest annotated JPEGs for media serving | Overwritten continuously |
| AWS S3 | Iceberg data files, sampled frames, optional clips | Long-lived object storage |
| Iceberg | Analytical tables | Historical |
| Trino | SQL query access over Iceberg | Query layer |

## Redis Realtime Keys

```text
stats:count:{camera_id}
live:frame:{camera_id}
heatmap:live:{camera_id}
track:active:{camera_id}:{track_id}
alerts:recent:{camera_id}
alerts:recent:store:{store_id}
alerts:cooldown:{camera_id}:{alert_type}
```

Redis is not the historical source of truth. Keys expire so dashboard state naturally goes stale when a camera, Vision worker, or realtime job stops.

## Local Live Media

Vision writes annotated frames to:

```text
runtime/live_frames/{camera_id}.jpg
runtime/live_frames/{camera_id}.json
```

FastAPI reads these files for:

- WebRTC video track prototype.
- MJPEG fallback stream.
- Snapshot endpoint.
- Media freshness metrics.

This keeps video bytes out of Redis and Flink.

## AWS S3

AWS S3 stores:

```text
lakehouse/      Iceberg warehouse root
frames/         optional sampled JPEGs
clips/          optional alert clips
```

The bucket currently used by config is `retail-video-analytics-prod`.

## Iceberg And Trino

Iceberg tables hold historical analytical data. Trino is used to query them through the `lakehouse` catalog.

Current tables:

```text
lakehouse.rva.bronze_raw
lakehouse.rva.silver_detections
lakehouse.rva.gold_track_summary
lakehouse.rva.gold_camera_hourly_metrics
lakehouse.rva.gold_camera_daily_metrics
lakehouse.rva.gold_camera_daily_dwell
lakehouse.rva.gold_alert_events
```

## Serving Access Pattern

| Use case | Source |
|---|---|
| Live count | Redis or live media metadata fallback |
| Active tracks | Redis key scan |
| Live heatmap | Redis sorted set |
| Recent alerts | Redis recent alert lists |
| Current video | Local latest JPEG served by FastAPI |
| Historical detections | Trino over Iceberg |
| Track summary analytics | Trino over `gold_track_summary` |
| Alert history | Trino over `gold_alert_events` |
| Sampled frame lookup | AWS S3 object paths |
| Alert clip replay | AWS S3 object paths linked by alert metadata |
