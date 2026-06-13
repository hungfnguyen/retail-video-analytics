# Supervision Vision Rebuild Documentation

> Status: historical implementation-planning notes. The current lakehouse source
> of truth is `docs/lakehouse/README.md`, especially the v2 tables
> `silver_detections_v2`, `gold_track_summary_v2`, `gold_queue_sessions`,
> `gold_alerts`, and `lakehouse.rva_gold_serving.*`.

This directory is the implementation planning set for rebuilding
`services/vision/` around Supervision and Roboflow Trackers.

The main decision is that Vision becomes a feature extraction layer for the
retail data platform. It should emit structured facts, not only person boxes:

```text
frame
  -> detections
  -> tracked identities
  -> bottom-center anchors
  -> zone membership
  -> line crossings
  -> queue snapshots
  -> quality metrics
  -> Pulsar events
```

The downstream platform remains the system of record for streaming state,
realtime serving, and historical analytics:

```text
Vision -> Pulsar -> Flink -> Redis + Iceberg -> Trino -> FastAPI -> React
```

## Reading Order

| Doc | Purpose |
|---|---|
| [01_VISION_REBUILD_ARCHITECTURE.md](./01_VISION_REBUILD_ARCHITECTURE.md) | Target Vision module architecture and boundaries |
| [02_SUPERVISION_AND_TRACKERS_USAGE.md](./02_SUPERVISION_AND_TRACKERS_USAGE.md) | How to use Supervision and Roboflow Trackers safely |
| [03_TRACKING_QUALITY_AND_GLOBAL_ID.md](./03_TRACKING_QUALITY_AND_GLOBAL_ID.md) | Tracking quality, frame dropping, and global ID stabilization |
| [04_ZONE_LINE_QUEUE_ANALYTICS_DESIGN.md](./04_ZONE_LINE_QUEUE_ANALYTICS_DESIGN.md) | Polygon zones, line crossings, and queue feature extraction |
| [05_EVENT_CONTRACT_V2.md](./05_EVENT_CONTRACT_V2.md) | Event schema v2 for richer Vision facts |
| [06_STREAMING_REALTIME_SERVING_V2.md](./06_STREAMING_REALTIME_SERVING_V2.md) | Flink realtime and Redis serving changes |
| [07_LAKEHOUSE_ZONE_QUEUE_TABLES.md](./07_LAKEHOUSE_ZONE_QUEUE_TABLES.md) | Iceberg Silver/Gold table expansion |
| [08_IMPLEMENTATION_ROADMAP_AND_TEST_PLAN.md](./08_IMPLEMENTATION_ROADMAP_AND_TEST_PLAN.md) | Phased build plan, tests, and acceptance criteria |

## Core Pipeline

```text
FrameSource
  -> DetectorAdapter
      YOLO/RF-DETR/custom model -> sv.Detections
  -> DetectionFilter
      person class, confidence, optional NMS
  -> TrackerAdapter
      ByteTrackTracker / BoT-SORT / OC-SORT
  -> DetectionsSmoother
  -> GlobalIdStabilizer
  -> AnchorExtractor
      bottom-center by default
  -> PolygonZoneManager
  -> LineZoneManager
  -> FeatureBuilder
      frame metrics, zone counts, queue snapshot, line crossings
  -> EventBuilder
      DetectionFrameEvent v1/v2
  -> Publishers
      Pulsar metadata, live frame writer, optional debug sinks
```

## Design Principles

- Supervision is the Vision data model, annotation, geometry, and debug tooling
  layer.
- Roboflow Trackers is the production tracking layer because current
  Supervision docs deprecate `sv.ByteTrack`.
- Vision emits facts; Flink owns stateful sessions, queue wait time, dwell time,
  and historical aggregates.
- Raw video remains outside Pulsar/Flink/Redis. Vision writes annotated latest
  JPEGs for the media plane.
- The migration must keep the current v1 event path usable until Flink and API
  are ready for v2.

## External References

- https://supervision.roboflow.com/develop/how_to/detect_and_annotate/
- https://supervision.roboflow.com/develop/how_to/track_objects/
- https://supervision.roboflow.com/develop/how_to/save_detections/
- https://supervision.roboflow.com/develop/how_to/count_in_zone/
- https://supervision.roboflow.com/develop/trackers/
- https://trackers.roboflow.com/develop/learn/detection-quality/
- https://trackers.roboflow.com/develop/learn/track/
- https://blog.roboflow.com/monitor-retail-queues/
