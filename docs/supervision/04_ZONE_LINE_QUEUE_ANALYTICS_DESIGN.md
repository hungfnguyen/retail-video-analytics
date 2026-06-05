# Zone Line Queue Analytics Design

## Goal

Convert frame-level person detections into retail facts:

```text
zone membership
zone occupancy
line crossings
queue snapshots
```

This changes Vision output from raw geometry into business-aware metadata that
Flink can turn into sessions, live metrics, and historical analytics.

## Zone Configuration

Store zone definitions in a dedicated config:

```text
configs/zones.yaml
```

Use normalized coordinates so camera resolution changes do not invalidate the
configuration.

Example:

```yaml
version: "zones-2026-06-v1"

stores:
  store_001:
    cameras:
      cam_01:
        resolution:
          width: 1280
          height: 720

        zones:
          - zone_id: checkout_queue_01
            zone_name: Checkout Queue 01
            zone_type: queue
            priority: 100
            trigger_anchor: bottom_center
            polygon_norm:
              - [0.55, 0.42]
              - [0.92, 0.44]
              - [0.96, 0.88]
              - [0.50, 0.90]

        lines:
          - line_id: entrance_line_01
            line_name: Main Entrance Line
            line_type: entrance_exit
            start_norm: [0.05, 0.78]
            end_norm: [0.35, 0.74]
            direction_in: left_to_right
```

Use the Roboflow PolygonZone web utility for camera calibration:

```text
extract first frame -> upload frame -> draw zones/lines -> copy normalized points
```

## Anchors

Use bottom-center as the default anchor:

```text
x = (bbox.x1 + bbox.x2) / 2
y = bbox.y2
```

Reason:

- bbox centroid can fall on the body, shelf, or adjacent lane;
- bottom-center approximates the shopper foot position;
- retail zones usually represent floor areas.

Keep centroid fields for backward compatibility and heatmap continuity.

## Polygon Zones

Use `PolygonZone` for:

- checkout queue occupancy;
- aisle occupancy;
- promotion area dwell;
- entrance area count;
- cashier counter proximity.

For each frame:

```text
zone.trigger(detections) -> mask
mask -> detection zone assignments
mask.sum() -> zone count
```

If zones overlap, choose the primary zone by highest priority. Keep all matched
zones in the event for debugging and future analytics.

## Line Zones

Use `LineZone` for:

- entrance in/out;
- queue entry/exit;
- movement between major areas;
- checkout completion proxy.

Line crossing requires stable tracker IDs, so line logic runs only after tracker
update and global ID stabilization.

Line event:

```json
{
  "line_id": "entrance_line_01",
  "line_type": "entrance_exit",
  "direction": "in",
  "track_id": 12,
  "global_track_id": "cam_01_g_000012"
}
```

## Queue Snapshot

Vision should emit current queue facts, not durable queue sessions.

Vision emits:

- detection is currently in queue zone;
- frame-level queue zone count;
- oldest active queue track if available from local short state;
- line crossing into/out of queue when configured.

Flink computes:

- queue session start;
- queue session update;
- queue session close;
- wait time;
- grace-period handling;
- aggregate queue metrics.

## Vision Facts

Frame-level facts:

```text
people_count
zone_counts[]
line_crossings[]
queue_snapshot[]
frame_metrics
```

Detection-level facts:

```text
anchor
zones[]
primary_zone_id
queue.in_queue
quality flags
global_track_id
```

## Downstream Metrics

Safe without stable ID:

- current count per zone;
- current checkout queue length;
- frame-level crowding;
- live occupancy cards.

Requires stable/global ID:

- unique visitors per zone;
- dwell time;
- queue wait time;
- line crossing per person;
- customer journey;
- conversion path.

## Zone Flicker Controls

Use these controls to avoid noisy metrics near boundaries:

- bottom-center anchor;
- detection smoothing after tracking;
- zone priority when polygons overlap;
- optional local zone stability over N frames;
- Flink exit grace of `1000-2000 ms`;
- queue session minimum duration of about `3000 ms`.

