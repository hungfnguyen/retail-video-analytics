# Tracking Quality And Global ID

## Problem Statement

The current issue is intermittent person detection and unstable IDs:

```text
person is visible by eye
  -> detector misses or tracker loses a few frames
  -> tracker emits a new track_id
  -> downstream treats one shopper as multiple tracks
```

This breaks dwell time, queue wait time, unique visitor count, customer journey,
and Gold track summaries.

## Root Causes To Measure

Do not assume the tracker is the only problem. Measure these separately:

- detector miss: person is visible but `raw_detection_count` drops to zero;
- tracker reset: detections continue but IDs restart unexpectedly;
- frame dropping: effective FPS is too low or frame gaps are irregular;
- threshold mismatch: low-confidence boxes are removed before the tracker can use them;
- occlusion/crowding: shoppers overlap or cross paths;
- bbox jitter: IDs stay stable but boxes/anchors move noisily.

The current bounded queue with `frame_queue_size=1` is a major suspect. It is
good for freshness, but it can make object motion too discontinuous for IoU-based
association when inference is slow.

## Baseline Metrics

Before changing production behavior, add a benchmark script that records:

```text
frame_index
source_frame_index
capture_ts
source_fps
effective_fps
dropped_frames_since_last
raw_detection_count
tracked_detection_count
track_ids
new_track_ids
lost_track_ids
avg_track_duration_sec
inference_ms
tracking_ms
total_ms
```

For manual review, export an annotated debug video with boxes, labels, traces,
track IDs, global IDs, zones, and frame metrics.

Use at least three videos:

- low crowd, no occlusion;
- checkout queue;
- crowded/occluded movement.

## Detector First

Tracking quality starts with detector quality. If YOLO misses people, tracking
cannot reliably preserve IDs.

Detector actions to test:

- lower detector confidence to `0.10-0.20`;
- use `classes=[0]` for person-only filtering;
- increase `imgsz` to `1280` or `1536`;
- enable half precision on GPU;
- enable `InferenceSlicer` for wide cameras;
- fine-tune on retail frames if miss rate remains high;
- evaluate RF-DETR or another model if YOLO misses small/far people.

## Tracker Baseline

Start with ByteTrack:

```yaml
type: bytetrack
track_activation_threshold: 0.20
lost_track_buffer: 60
minimum_consecutive_frames: 2
frame_rate: effective_fps
```

Tune rules:

- increase `lost_track_buffer` to `90` or `120` if IDs break after short occlusion;
- increase `minimum_consecutive_frames` to `3` or `5` if many false tracks appear;
- evaluate BoT-SORT/ReID if adjacent shoppers frequently swap IDs;
- evaluate OC-SORT if motion is abrupt or nonlinear.

The tracker must be initialized once per camera worker and reset only on source
restart or worker restart.

## Frame Policy

Define two frame policies:

```text
latest_only
  lowest latency
  may drop many intermediate frames
  useful for media demo

tracking_safe
  bounded queue of 4-8 frames
  controlled dropping
  records skipped source frames
  better for stable tracking
```

Default production profile should be `tracking_safe` unless camera-to-dashboard
latency is unacceptable.

Tracker `frame_rate` should approximate effective processed FPS, not the source
FPS, when the service cannot process every frame.

## Global Track ID

Raw tracker IDs are not stable enough for business metrics. Add:

```text
track_id
  raw tracker-assigned ID

global_track_id
  application-stabilized ID for short broken tracks
```

Example:

```text
track_id=12 -> global_track_id=cam_01_g_000042
track_id=31 -> global_track_id=cam_01_g_000042
```

## Reconnect Rule

When a new raw track appears, compare it to recently lost tracks:

```text
time_gap_ms <= max_reconnect_gap_ms
bottom-center distance <= max_reconnect_distance_px
bbox area ratio delta <= max_bbox_area_ratio_delta
same or adjacent zone if zone data exists
motion direction is compatible when enough history exists
```

Recommended baseline:

```yaml
global_id:
  enabled: true
  max_reconnect_gap_ms: 2000
  max_reconnect_distance_px: 120
  max_bbox_area_ratio_delta: 0.50
  require_same_or_adjacent_zone: true
```

## Business Metric Rule

Use `global_track_id` for:

- queue wait time;
- dwell time;
- unique visitor count;
- customer journey;
- zone transition;
- Gold session tables.

Use raw `track_id` only for low-level tracking diagnostics and debugging.

## Future Calibration

If homography or 3D projection is added, replace pixel-distance reconnect logic
with floor-plane distance:

```text
bottom-center pixel -> world coordinate -> distance in meters
```

This improves reconnect decisions across perspective distortion.

