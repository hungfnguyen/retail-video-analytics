# Target Architecture

This document describes the current target architecture implemented in the repository.

## Architecture

```text
                         Camera / Video Files
                                  |
                                  v
                         Vision Service
                  YOLO11 detection + tracking
                   |              |             |
                   |              |             |
                   v              v             v
            Pulsar events   sampled media   latest annotated JPEG
                   |          AWS S3         runtime/live_frames
          +--------+--------+                    |
          |                 |                    v
          v                 v                 FastAPI media
  Flink lakehouse     Flink realtime          WebRTC/MJPEG
  Table API jobs      DataStream job             |
          |                 |                    v
          v                 v               React Live UI
  Iceberg on AWS S3   Redis live state
          |
          v
        Trino
```

## Component Responsibilities

| Component | Responsibility |
|---|---|
| Vision service | Reads camera/video frames, runs detection/tracking, publishes metadata, writes live media |
| Pulsar | Durable metadata transport between Vision and Flink |
| Flink lakehouse jobs | Persist raw events, flatten enriched detections, aggregate Gold facts |
| Flink realtime job | Build low-latency Redis state and route invalid events to DLQ |
| Redis | Current count, active tracks, heatmap, latest frame snapshot |
| Iceberg REST | Catalog for Iceberg tables stored on AWS S3 |
| AWS S3 | Iceberg table data, sampled frames, optional clips |
| Trino | SQL query engine for lakehouse data and Gold serving refreshes |
| FastAPI | Backend-for-frontend, live API, WebRTC/MJPEG gateway |
| React frontend | Live monitoring, analytics UI, system UI |

## Dual Path Design

### Realtime Path

```text
Pulsar -> RealtimeMetricsJob -> Redis -> FastAPI -> React Live page
```

This path optimizes low latency. It is suitable for current count, active tracks, live heatmap, and dashboard freshness indicators.

### Lakehouse Path

```text
Pulsar -> BronzeIngestJob -> bronze_raw
bronze_raw -> SilverJob -> silver_detections_v2
silver_detections_v2 -> GoldTrackSummaryJob -> gold_track_summary_v2
silver_detections_v2 -> QueueAnalyticsJob -> gold_queue_sessions_v2
silver_detections_v2 + gold_track_summary_v2 -> GoldDashboardAggregateJob -> dashboard Gold facts
media-events -> GoldAlertsJob -> gold_alerts
Gold facts / Silver -> gold_serving_* -> FastAPI analytics
```

This path optimizes correctness, auditability, replay, and SQL analysis. Latency is governed by Flink checkpoints and Iceberg commit cycles.

`gold_serving_*` tables live in `lakehouse.rva_gold_serving`. They are query-ready
Gold tables for analyst dashboards, not a separate medallion tier.

## Current Deployment Boundary

`docker-compose.yml` runs infrastructure services:

- Pulsar
- Flink JobManager/TaskManager/job submitter
- Redis
- Iceberg REST
- Trino

Vision, FastAPI, and Frontend run as local development processes. This keeps GPU/CV runtime and frontend iteration separate from the data infrastructure stack.

## Design Decisions

| Decision | Reason |
|---|---|
| Store metadata, not raw video, in lakehouse | Smaller, queryable, aligned with Data Engineering objectives |
| Keep video media outside Flink/Redis | Video bytes are media-plane data, not stream analytics state |
| Use Redis for live state | Low-latency TTL state fits dashboard needs |
| Use Iceberg on AWS S3 | Supports table snapshots, schema evolution, Trino reads |
| Use React as the only dashboard UI | Single UI surface for live, analytics, and system views |
| Use WebRTC first, MJPEG fallback | Better browser media path while preserving simple local fallback |
