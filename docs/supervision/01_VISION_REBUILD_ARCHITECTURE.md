# Vision Rebuild Architecture

## Current State

The current Vision service is an edge pipeline:

```text
VideoFileReader
  -> bounded queue
  -> Ultralytics model.track(persist=True)
  -> local raw object dicts
  -> TrackMemory
  -> DetectionFrameEvent-compatible dicts
  -> Pulsar
  -> OpenCV Visualizer
  -> runtime/live_frames
```

This works for a basic realtime dashboard, but it mixes detector, tracker,
application track memory, event conversion, annotation, and media writing in one
worker loop.

The main technical risks are:

- `model.track(persist=True)` hides tracker internals and makes ByteTrack,
  BoT-SORT, and OC-SORT hard to benchmark consistently.
- Raw dictionaries are used as the internal Vision representation, so every
  downstream feature must reimplement its own field handling.
- `frame_queue_size=1` prioritizes freshness but can damage tracker continuity
  when inference cannot keep up.
- `TrackMemory` stitches short gaps using IoU and center distance only; it is
  useful but not enough for crowded crossings or long occlusion.
- Annotation is custom OpenCV drawing, so zone, line, trace, and debug overlays
  are local reimplementations.

## Target Responsibility

After the rebuild, `services/vision/` should be the edge feature extraction
service for the data platform.

Vision owns:

- frame read and timestamping;
- detector execution;
- conversion to `sv.Detections`;
- person filtering and optional inference slicing;
- tracker update with one tracker instance per camera worker;
- detection smoothing;
- `global_track_id` stabilization for short tracking gaps;
- bottom-center anchor extraction;
- semantic polygon-zone assignment;
- line crossing detection;
- frame-level queue snapshot facts;
- event v1/v2 construction;
- annotated latest JPEG and live frame metadata;
- optional debug CSV/JSON/video artifacts.

Vision does not own:

- queue session close/open history;
- dwell-time history;
- hourly or daily aggregates;
- Redis serving state;
- Iceberg table writes;
- Trino analytics;
- long-term unique visitor identity across cameras or stores.

Those responsibilities belong to Flink, Redis, Iceberg, Trino, FastAPI, and
React.

## Target Data Flow

```text
Camera / video / RTSP
  -> FrameSource
  -> DetectorAdapter
  -> sv.Detections
  -> DetectionFilter
  -> TrackerAdapter
  -> DetectionsSmoother
  -> GlobalIdStabilizer
  -> AnchorExtractor
  -> PolygonZoneManager
  -> LineZoneManager
  -> FeatureBuilder
  -> EventBuilder
  -> PulsarPublisher
  -> LiveFrameWriter
  -> DebugSinks
```

Downstream:

```text
Pulsar event
  -> Flink realtime v1/v2 parser
  -> Redis live state
  -> Flink lakehouse path
  -> Iceberg Bronze/Silver/Gold
  -> Trino
  -> FastAPI
  -> React
```

## Proposed Package Structure

The production rewrite should move toward a clean package layout:

```text
services/vision/src/rva_vision/
  config/
  runtime/
  sources/
  detection/
  tracking/
  geometry/
  zones/
  features/
  schemas/
  emit/
  media/
  observability/
  utils/
```

The current top-level files can remain during migration, but new code should be
introduced behind clear adapters so the worker loop is not a single large
procedural block.

## Stable Interfaces

The rewrite should preserve these stable concepts:

```python
class Detector:
    def predict(self, frame) -> "sv.Detections": ...

class MultiObjectTracker:
    def update(self, detections) -> "sv.Detections": ...
    def reset(self) -> None: ...

class DetectionFrameEventBuilder:
    def build(self, frame_packet, features): ...
```

Keep direct Supervision/Trackers usage inside adapters:

- `detection/yolo_detector.py`
- `tracking/bytetrack_adapter.py`
- `zones/polygon_zone_manager.py`
- `zones/line_zone_manager.py`
- `media/annotator.py`

This reduces risk if external APIs change.

## Migration Boundary

Phase 1 must keep event schema v1 compatible. That lets the existing Flink,
Redis, FastAPI, and React path continue working while Vision internals are
rewritten around `sv.Detections`.

Event v2 should be introduced only after:

- baseline tracking metrics exist;
- `sv.Detections` conversion is stable;
- tracker adapter is stable;
- zone/line feature extraction is tested;
- Flink parsers can accept v1 and v2.

