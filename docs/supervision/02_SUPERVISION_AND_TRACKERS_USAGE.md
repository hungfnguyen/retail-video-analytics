# Supervision And Trackers Usage

## Core Decision

Use Supervision as the common computer vision data layer, not as a complete
replacement for the data platform.

Use Roboflow Trackers as the production multi-object tracking layer.

```text
Ultralytics YOLO / RF-DETR / custom detector
  -> sv.Detections
  -> trackers.ByteTrackTracker / BoT-SORT / OC-SORT
  -> Supervision smoothing, geometry, annotation, debug sinks
```

Supervision does not make the detector more accurate by itself. If the detector
misses a shopper for several frames, the tracker has limited information to
recover the ID.

## `sv.Detections`

`sv.Detections` should be the canonical in-memory representation after model
inference.

Expected fields used by this project:

- `xyxy` for pixel bounding boxes;
- `confidence` for detection score;
- `class_id` for person filtering;
- `tracker_id` after tracker update;
- `data` for optional local metadata when useful.

Typical detector flow:

```python
result = model.predict(frame, classes=[0], conf=0.15, imgsz=1280)[0]
detections = sv.Detections.from_ultralytics(result)
detections = detections[detections.class_id == 0]
```

The event builder maps `sv.Detections` to the existing contract:

```text
xyxy -> bbox
xyxy / image_size -> bbox_norm
confidence -> conf
class_id -> class_id
tracker_id -> track_id
bottom-center -> anchor
```

## Roboflow Trackers

Current Supervision docs mark `sv.ByteTrack` as deprecated and recommend the
separate `trackers` package.

Production baseline:

```python
from trackers import ByteTrackTracker

tracker = ByteTrackTracker(
    track_activation_threshold=0.20,
    lost_track_buffer=60,
    minimum_consecutive_frames=2,
)
detections = tracker.update(detections)
```

Start with ByteTrack because it is fast and strong for retail CCTV where
confidence can fluctuate. Evaluate BoT-SORT/ReID after the ByteTrack baseline is
measured.

The tracker instance must live for the full lifetime of one camera worker. It
must not be recreated per frame.

## `DetectionsSmoother`

Use Supervision's smoother only after tracker assignment:

```text
detector -> tracker -> smoother
```

It smooths boxes and anchors for the same `tracker_id`. It does not solve an ID
switch after the tracker has already assigned the wrong ID.

Benefits:

- less bbox jitter;
- less bottom-center anchor jitter;
- fewer zone-boundary flickers;
- cleaner annotated live video.

## Polygon Zones

Use `PolygonZone` for semantic retail areas:

- checkout queue;
- entrance area;
- aisle;
- promotion area;
- cashier counter;
- cold drink area.

`zone.trigger(detections)` returns a boolean mask for detections inside the
polygon. This is used to assign zone membership and frame-level zone counts.

Use bottom-center as the default trigger anchor because it approximates the
shopper's foot position on the floor better than bbox centroid.

## Line Zones

Use `LineZone` for crossing facts:

- entrance in/out;
- queue entry/exit;
- aisle transition;
- checkout completion.

Line crossing depends on `detections.tracker_id`, so it should run after tracker
update and after any global-ID stabilization metadata is available.

## Annotators

Use Supervision annotators for live frame and debug video output:

- `BoxAnnotator`;
- `LabelAnnotator`;
- `TraceAnnotator`;
- `PolygonZoneAnnotator`;
- `LineZoneAnnotator`.

Annotated media stays in the media plane:

```text
runtime/live_frames/{camera_id}.jpg
runtime/live_frames/{camera_id}.json
```

Video bytes must not go through Pulsar, Flink, or Redis.

## Debug Sinks

Use `CSVSink` and `JSONSink` for offline evaluation, not production serving.

Use cases:

- tracker benchmark exports;
- thesis evaluation artifacts;
- comparison of detector/tracker configs;
- reproducible debug data for a problematic camera.

Production metadata still goes through Pulsar and Iceberg.

## Optional Inference Slicer

Use `InferenceSlicer` only per camera profile.

Enable it when:

- camera is wide angle;
- people are small or far away;
- full-frame resize loses detail;
- detector miss rate is high for distant shoppers.

Do not enable it by default because it increases compute cost and can reduce
effective FPS.

