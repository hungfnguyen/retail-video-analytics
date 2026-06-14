# Retail Video Analytics Documentation

This directory documents the current implementation of the project. It intentionally describes the deployed architecture only: Vision, Pulsar, Flink, Redis, Iceberg on AWS S3, Trino, FastAPI, and React.

## Recommended Reading Order

| Doc | Purpose |
|---|---|
| [00_THESIS_SCOPE.md](./00_THESIS_SCOPE.md) | Scope and boundaries of the implemented system |
| [01_TARGET_ARCHITECTURE.md](./01_TARGET_ARCHITECTURE.md) | Current end-to-end architecture |
| [02_DATA_FLOW_AND_CONTRACTS.md](./02_DATA_FLOW_AND_CONTRACTS.md) | Event contracts and storage contracts |
| [03_STREAMING_PIPELINE.md](./03_STREAMING_PIPELINE.md) | Flink realtime and lakehouse paths |
| [04_LAKEHOUSE_DESIGN.md](./04_LAKEHOUSE_DESIGN.md) | Iceberg tables currently implemented |
| [05_OPERATIONAL_STORAGE.md](./05_OPERATIONAL_STORAGE.md) | Redis, local live media, AWS S3, and Trino serving storage |
| [06_CAMERA_EDGE_PROCESSING.md](./06_CAMERA_EDGE_PROCESSING.md) | Vision worker processing flow |
| [07_DASHBOARD_AND_SERVING.md](./07_DASHBOARD_AND_SERVING.md) | FastAPI and React dashboard serving layer |
| [08_IMPLEMENTATION_ROADMAP.md](./08_IMPLEMENTATION_ROADMAP.md) | Remaining implementation roadmap |
| [09_EVALUATION_PLAN.md](./09_EVALUATION_PLAN.md) | Evaluation and verification plan |
| [10_S3_INFRASTRUCTURE.md](./10_S3_INFRASTRUCTURE.md) | AWS S3 layout and permissions |
| [11_VISION_MULTI_CAMERA_FLOW.md](./11_VISION_MULTI_CAMERA_FLOW.md) | Multi-camera Vision architecture |
| [12_DATA_EXTRACTION_DESIGN.md](./12_DATA_EXTRACTION_DESIGN.md) | How raw video becomes structured metadata |
| [13_FLINK_API_GUIDE.md](./13_FLINK_API_GUIDE.md) | Flink API choices and job patterns |
| [LOCAL_RUN_GUIDE.md](./LOCAL_RUN_GUIDE.md) | Local run and verification checklist |

## Current Architecture Summary

```text
Camera/video files
  -> Vision service
      -> Pulsar detection events
      -> latest annotated JPEG files
      -> optional sampled media on AWS S3

Pulsar
  -> Flink lakehouse path -> Iceberg tables on AWS S3 -> Trino
  -> Flink realtime path -> Redis -> FastAPI

FastAPI
  -> live dashboard JSON
  -> WebRTC/MJPEG media endpoints

React frontend
  -> Live page connected to realtime data
  -> Analytics page backed by Gold aggregate tables
  -> System page backed by service health data
```

## Implemented Iceberg Tables

```text
lakehouse.rva.bronze_raw
lakehouse.rva.silver_detections_v2
lakehouse.rva.gold_track_summary_v2
lakehouse.rva.gold_queue_sessions
lakehouse.rva.gold_camera_hourly_metrics
lakehouse.rva.gold_camera_daily_metrics
lakehouse.rva.gold_camera_daily_dwell
lakehouse.rva.gold_alert_events
lakehouse.rva.gold_alerts
lakehouse.rva_gold_serving.gold_serving_*
```

`lakehouse.rva_gold_serving.*` is the physical namespace for Gold serving tables.
It is still part of the Gold layer, not a fourth medallion tier.

## Implemented Realtime Redis Keys

```text
stats:count:{camera_id}
live:frame:{camera_id}
heatmap:live:{camera_id}
track:active:{camera_id}:{track_id}
alerts:recent:{camera_id}
alerts:recent:store:{store_id}
alerts:cooldown:{camera_id}:{alert_type}
```
