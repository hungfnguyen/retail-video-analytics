# Vision Supervision Rewrite Plan

## Goal

Rewrite the Vision module around `supervision.Detections` as the canonical
in-memory detection format while preserving the existing downstream event
contract:

```text
Vision -> Pulsar DetectionFrameEvent -> Flink -> Redis/Iceberg -> FastAPI/React
```

The rewrite should improve maintainability and tracking observability first.
Tracking stability should improve through better tracker choice, frame handling,
and tuning, not by assuming Supervision alone improves model accuracy.

## Source Findings

Official Supervision docs describe Supervision as a Python library for building
computer vision applications. Its key value for this project is a unified
`Detections` object, model-output converters such as `from_ultralytics`,
annotators, video utilities, polygon/line zone tools, trackers, smoothing, and
metrics.

Relevant references:

- https://supervision.roboflow.com/latest/
- https://supervision.roboflow.com/latest/detection/core/
- https://supervision.roboflow.com/latest/trackers/
- https://supervision.roboflow.com/latest/detection/tools/smoother/
- https://supervision.roboflow.com/latest/detection/tools/polygon_zone/
- https://supervision.roboflow.com/latest/utils/video/
- https://github.com/roboflow/trackers
- https://trackers.roboflow.com/latest/learn/track/
- https://trackers.roboflow.com/latest/trackers/comparison/

Key implications:

- Supervision standardizes detector output but does not make the detector more
  accurate by itself.
- `DetectionsSmoother` requires `tracker_id`; it smooths boxes/confidence after
  tracking and does not solve identity switches alone.
- Polygon/line zones also depend on stable `tracker_id` for track-aware
  behavior.
- Roboflow `trackers` is a stronger candidate for tracker replacement than
  Supervision's built-in ByteTrack alone because it exposes modular
  implementations for ByteTrack, OC-SORT, BoT-SORT, and SORT with a native
  `supervision.Detections` interface.

## Current Vision Problems

Current code path:

```text
VideoFileReader
  -> queue(maxsize=frame_queue_size)
  -> Ultralytics model.track(persist=True)
  -> raw object dicts
  -> TrackMemory
  -> DetectionFrameEvent dicts
  -> Pulsar
  -> Visualizer/OpenCV annotated JPEG
```

Observed risk points:

- `frame_queue_size` is currently `1`, so slow inference drops frames by design.
  Frame drops increase motion gaps and can cause trackers to lose IDs.
- `model.track(persist=True)` hides tracker internals behind Ultralytics, making
  it harder to benchmark ByteTrack/BoT-SORT/OC-SORT consistently.
- Current `TrackMemory` stitches lost IDs with IoU and center distance only. It
  can bridge short gaps but cannot reliably solve crowded crossings or long
  occlusion.
- BoT-SORT config has ReID enabled but global motion compensation is disabled.
  This is acceptable for fixed cameras, but not for shaky or moving sources.
- Annotation is custom OpenCV code, so trace, zone, label, and heatmap features
  require local reimplementation.

## Recommended Architecture

Use Supervision as the common CV data layer, not as a downstream system layer.

```text
FrameSource
  -> DetectorAdapter
      YOLO/RF-DETR/etc -> sv.Detections
  -> DetectionFilter
      class/conf/NMS/zone prefilter
  -> TrackerAdapter
      trackers.ByteTrackTracker | OCSORTTracker | BoTSORTTracker
      -> sv.Detections with tracker_id
  -> Optional DetectionsSmoother
  -> StableTrackPolicy
      short gap bridge, lifecycle metrics, predicted tracks if needed
  -> EventBuilder
      sv.Detections -> DetectionFrameEvent-compatible dicts
  -> MediaAnnotator
      Supervision annotators -> latest JPEG
  -> Publishers
      Pulsar metadata, optional S3 sampled media/clips
```

Keep these boundaries:

- Vision owns frame read, detection, tracking, local media, and event creation.
- Pulsar event schema remains compatible with current Flink jobs.
- Flink/Redis/Iceberg do not receive video bytes.
- FastAPI media endpoints continue reading latest annotated JPEGs.

## Proposed Module Layout

```text
services/vision/
  app/
    worker.py                 per-camera orchestration
    lifecycle.py              signal handling and worker shutdown
  sources/
    base.py                   FrameSource protocol
    opencv_source.py          video file / RTSP source
  detection/
    ultralytics_detector.py   YOLO -> sv.Detections
    filters.py                class/conf/NMS helpers
  tracking/
    adapter.py                tracker factory and common interface
    stable_memory.py          optional bridge for short detector gaps
    metrics.py                ID switch/drop/flicker counters
  analytics/
    zones.py                  PolygonZone/LineZone definitions
    heatmap.py                optional local per-frame heatmap helpers
  events/
    builder.py                sv.Detections -> core.models payload
  media/
    annotator.py              Supervision Box/Label/Trace annotators
    live_frame_publisher.py   keep existing atomic JPEG writer
  publish/
    pulsar.py                 keep existing PulsarEmitter behavior
```

This layout isolates detector, tracker, event contract, and media serving. It
also makes benchmark scripts easier to write.

## Tracker Strategy

Phase 1 should compare three trackers on the same videos:

| Tracker | Why test it |
|---|---|
| ByteTrack | Good default for noisy confidence and brief weak detections |
| OC-SORT | Better candidate when IDs break due to nonlinear motion or abrupt movement |
| BoT-SORT | Best candidate if camera motion or stronger identity stability matters |

Do not keep using `model.track(persist=True)` as the primary API in the rewrite.
Run detection separately:

```python
result = model(frame, conf=detector_conf, classes=class_filter, verbose=False)[0]
detections = sv.Detections.from_ultralytics(result)
detections = tracker.update(detections, frame=frame)
```

For Supervision built-in ByteTrack, the API is:

```python
tracker = sv.ByteTrack(frame_rate=fps)
detections = tracker.update_with_detections(detections)
```

For Roboflow `trackers`, the API is:

```python
from trackers import ByteTrackTracker

tracker = ByteTrackTracker(lost_track_buffer=60, minimum_consecutive_frames=3)
detections = tracker.update(detections, frame=frame)
```

Prefer Roboflow `trackers` for the benchmark because it gives a consistent
interface across ByteTrack, OC-SORT, and BoT-SORT.

## Frame Handling

The current queue-drop strategy is useful for dashboard freshness but harmful
for tracker continuity. The rewrite should separate read FPS from tracking FPS:

- For live serving: keep a bounded queue, but record every drop and expose it in
  media metadata.
- For tracker stability: target a sustainable `tracking_fps`, e.g. 8-15 FPS on
  CPU or higher on GPU, and avoid random drops between consecutive tracking
  updates.
- If inference is slower than source FPS, intentionally sample at a fixed stride
  rather than allowing unpredictable queue replacement.

This gives trackers consistent time steps and makes tuning meaningful.

## Event Contract Mapping

`sv.Detections` fields map cleanly to the existing event contract:

| Event field | Source |
|---|---|
| `bbox` | `detections.xyxy[i]` |
| `conf` | `detections.confidence[i]` |
| `class_id` | `detections.class_id[i]` |
| `track_id` | `detections.tracker_id[i]` |
| `bbox_norm` | bbox divided by frame width/height |
| `centroid_norm` | bbox center divided by frame width/height |

The existing fields `track_state`, `measurement_source`, `missed_frames`, and
`is_predicted` can remain optional. If `StableTrackPolicy` emits predicted
tracks, mark them explicitly as predicted so downstream consumers can choose
whether to count them.

## What Supervision Should Replace

Replace:

- raw object dictionaries as the main in-memory representation;
- custom conversion from Ultralytics boxes to local dicts;
- custom OpenCV box/label drawing where Supervision annotators are enough;
- future zone counting and line crossing implementations;
- ad hoc smoother logic for matched detections.

Keep or adapt:

- `TrackMemory`, but move it behind a `StableTrackPolicy` and treat it as an
  optional application policy, not the core tracker.
- `PulsarEmitter`, because the output contract is already working.
- `LiveFramePublisher`, because atomic file writes match the existing media
  serving path.
- `FrameSampler` and `AlertClipExtractor`, unless media artifact handling is
  redesigned separately.

## Evaluation Plan

Before replacing production Vision behavior, build a benchmark command:

```text
uv run --package rva-vision python services/vision/tools/benchmark_tracking.py \
  --source data/videos/video1.mp4 \
  --model yolo11l.pt \
  --tracker bytetrack \
  --output runtime/benchmarks/video1_bytetrack.mp4 \
  --csv runtime/benchmarks/video1_bytetrack_tracks.csv
```

Record:

- processed FPS;
- frame drops;
- number of active tracks per frame;
- number of new IDs per minute;
- track fragmentation proxy: same spatial trajectory receiving many IDs;
- count flicker: absolute count delta between adjacent frames;
- optional manual review of annotated video.

Run the same source with:

- current Ultralytics `model.track(persist=True)`;
- Supervision `sv.ByteTrack`;
- Roboflow `trackers.ByteTrackTracker`;
- Roboflow `trackers.OCSORTTracker`;
- Roboflow `trackers.BoTSORTTracker` if available and dependency cost is
  acceptable.

## Migration Order

1. Add dependencies: `supervision` first, then `trackers` if compatible with
   Python 3.12 and project packaging.
2. Add benchmark script without touching production worker.
3. Implement `DetectorAdapter` and event mapping tests.
4. Implement tracker adapters and benchmark outputs.
5. Replace `Visualizer` with Supervision annotators.
6. Rewrite `worker.py` around the new pipeline while preserving Pulsar payloads.
7. Run local pipeline verification: Redis keys, live media, Pulsar events, and
   Flink validation.

## Decision

Use Supervision heavily, but do not rely on it alone to fix ID switching.

Recommended target:

```text
Ultralytics YOLO inference
  -> sv.Detections
  -> Roboflow trackers adapter
  -> optional DetectionsSmoother
  -> optional StableTrackPolicy
  -> current DetectionFrameEvent contract
```

This gives the project a cleaner Vision module and a real path to measure and
improve tracking continuity.
