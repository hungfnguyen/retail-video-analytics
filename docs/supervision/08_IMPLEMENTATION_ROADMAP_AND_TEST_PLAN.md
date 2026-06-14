# Implementation Roadmap And Test Plan

> Status: historical roadmap for the Vision Supervision rewrite. Some table names
> and acceptance criteria below predate the current lakehouse model. Use
> `docs/lakehouse/README.md` and `docs/lakehouse/05_IMPLEMENTATION_ROADMAP.md`
> for the current project roadmap.

## Phase 0: Baseline Current Vision

Goal: identify why IDs jump before changing production behavior.

Tasks:

- add or run a benchmark script against current Vision behavior;
- record raw detections, tracked detections, new/lost IDs, dropped frames, FPS,
  inference latency, and tracking latency;
- export annotated debug videos for manual review;
- test low-crowd, queue, and occlusion videos.

Acceptance:

- baseline report exists;
- top ID-jump cause is classified as detector miss, tracker reset, frame drop,
  threshold issue, or occlusion.

## Phase 1: Internal `sv.Detections`

Goal: refactor Vision internals without changing downstream event v1.

Tasks:

- add `Detector` adapter returning `sv.Detections`;
- convert Ultralytics result with `sv.Detections.from_ultralytics`;
- filter person class;
- build current event v1 from `sv.Detections`;
- keep Pulsar payload compatible with existing Flink jobs.

Acceptance:

- Redis count and live frame still update;
- current Flink realtime and lakehouse jobs do not break;
- `silver_detections` continues receiving rows.

## Phase 2: Roboflow Trackers

Goal: replace hidden `model.track(persist=True)` behavior with explicit tracker
state.

Tasks:

- add `trackers` dependency;
- implement ByteTrack adapter;
- keep one tracker instance per camera worker;
- set baseline tracker config;
- add `DetectionsSmoother`;
- add trace annotation for debug outputs.

Acceptance:

- average track duration improves on benchmark videos;
- unreasonable new ID count decreases;
- no tracker reset occurs per frame.

## Phase 3: Frame Policy

Goal: reduce tracking breaks caused by uncontrolled frame dropping.

Tasks:

- add `latest_only` and `tracking_safe` frame policies;
- use bounded queue of `4-8` frames for `tracking_safe`;
- record `source_frame_index` and `dropped_frames_since_last`;
- set tracker frame rate from effective processed FPS.

Acceptance:

- `tracking_safe` has more stable IDs than `latest_only`;
- latency remains acceptable for dashboard use;
- event metrics expose frame dropping.

## Phase 4: Polygon Zones

Goal: add semantic retail zone membership.

Tasks:

- add `configs/zones.yaml`;
- add first-frame extraction utility for zone calibration;
- implement polygon zone manager;
- convert normalized polygons to pixel polygons;
- call `zone.trigger(detections)`;
- emit detection zones and frame-level zone counts;
- annotate polygon overlays.

Acceptance:

- events contain `zone_counts`;
- detections contain zone assignments;
- live frame shows polygon overlays;
- no Redis/Flink changes are required for initial proof if event v1 compatibility
  is still being preserved.

## Phase 5: Line Zones

Goal: emit entrance/exit and queue entry/exit facts.

Tasks:

- add line definitions to `configs/zones.yaml`;
- implement line zone manager;
- trigger line crossing after tracking/global ID;
- emit `line_crossings`;
- annotate line overlays.

Acceptance:

- events contain line crossings;
- direction is correct on validation video;
- duplicate crossings are controlled by tracker/global ID state.

## Phase 6: Event Contract V2

Goal: version the richer Vision event contract.

Tasks:

- define Pydantic schema for v2;
- add `event_type`, `frame_metrics`, `zone_counts`, `line_crossings`,
  detection `anchor`, detection `zones`, detection `queue`, and
  `global_track_id`;
- update Flink parser to accept v1 and v2 during migration;
- keep Bronze raw ingest available.

Acceptance:

- Pulsar receives v2 payloads;
- Flink does not crash on v1 or v2;
- invalid events go to DLQ;
- Bronze stores complete v2 raw payload.

## Phase 7: Realtime V2

Goal: serve zone, queue, line, and active global track data live.

Tasks:

- extend realtime Redis sink;
- write `zone:count:{camera_id}`;
- write `queue:live:{camera_id}:{zone_id}`;
- write `line:count:{camera_id}:{line_id}:{window}`;
- write active tracks by `global_track_id`;
- extend FastAPI live schema;
- extend React Live page.

Acceptance:

- dashboard shows current zone counts;
- queue zones show current count and later wait metrics;
- line counters are visible;
- TTL behavior marks state stale when pipeline stops.

## Phase 8: Queue Sessions

Goal: compute queue wait sessions with Flink state.

Tasks:

- create QueueSessionJob or extend a suitable Flink job;
- key by store, camera, queue zone, and global track ID;
- maintain enter timestamp, last seen timestamp, and frame count;
- apply exit grace around `2000 ms`;
- write Redis live queue metrics;
- write Iceberg `gold_queue_sessions`.

Acceptance:

- queue sessions appear in Gold;
- wait time matches manual video review;
- sessions are not split by brief zone flicker or short ID reconnects.

## Phase 9: Lakehouse Analytics

Goal: power historical analytics from Iceberg/Trino.

Tasks:

- create `silver_detections_v2`;
- create `silver_line_crossings`;
- create zone, queue, line, journey, and camera-health Gold tables;
- add validation Trino queries;
- add FastAPI analytics endpoints.

Acceptance:

- Trino can answer top crowded zones, average wait, entrance traffic, dwell time,
  and tracking health questions;
- Analytics page can consume real endpoints instead of placeholders.

## Phase 10: Observability And Hardening

Goal: make Vision production-debuggable.

Tasks:

- add structured logs;
- expose frames processed, inference latency, tracking latency, publish failures,
  dropped frames, active tracks, new tracks, lost tracks;
- add worker health state;
- handle Pulsar/S3 backpressure explicitly;
- flush publishers and writers on shutdown.

Acceptance:

- camera-specific bottlenecks are visible;
- worker restart does not hang process manager;
- Pulsar or S3 slowdown does not cause unbounded crash loops.

## Unit Tests

Add focused tests for:

- bbox normalization;
- bottom-center anchor extraction;
- zone assignment;
- line crossing;
- event v2 schema;
- global ID reconnect;
- config validation.

## Integration Tests

Add tests for:

- video fixture to event payload;
- live frame writer outputs `.jpg` and `.json`;
- debug CSV/JSON sinks;
- Pulsar publish in local environment when available.

## E2E Scenarios

Run:

```text
docker compose up
run Vision on sample video
verify Pulsar events
verify Redis keys
verify Iceberg Bronze/Silver/Gold
verify FastAPI dashboard
verify React Live page
```

Extend the existing evaluation checklist with:

- zone count;
- queue current count;
- line crossings;
- `global_track_id`;
- tracking quality metrics.

## Thesis Metrics

Vision quality:

```text
processed_fps
dropped_frames_per_min
avg_inference_ms
p95_inference_ms
avg_tracking_ms
track_fragmentation_estimate
avg_track_duration_sec
```

Retail analytics:

```text
zone_occupancy
queue_length
avg_queue_wait_sec
max_queue_wait_sec
entrance_in_count
entrance_out_count
zone_dwell_time
customer_journey_transitions
```

Data engineering:

```text
Pulsar throughput
Flink processing latency
Redis update latency
Iceberg commit latency
DLQ rate
schema validation error rate
camera_to_dashboard_latency
```
