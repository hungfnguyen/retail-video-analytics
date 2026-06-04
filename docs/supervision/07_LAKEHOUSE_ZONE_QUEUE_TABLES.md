# Lakehouse Zone Queue Tables

## Goal

Extend the current Iceberg lakehouse from track summaries to retail zone and
queue analytics.

Current tables:

```text
lakehouse.rva.bronze_raw
lakehouse.rva.silver_detections
lakehouse.rva.gold_track_summary
```

V2 adds richer Silver tables and Gold tables for zones, queues, line crossings,
journeys, and camera health.

## Bronze

Keep Bronze as the raw source of truth:

```text
lakehouse.rva.bronze_raw
```

It stores raw v1/v2 JSON payloads so downstream parsing can evolve.

Recommended extracted headers:

```text
schema_version
event_type
event_id
pipeline_run_id
store_id
camera_id
capture_ts
ingest_ts
zone_config_version
model_name
tracker_type
payload
```

Bronze backfill remains the safest way to rebuild Silver/Gold tables.

## Silver Detections V2

Add:

```text
lakehouse.rva.silver_detections_v2
```

Columns:

```text
store_id
camera_id
capture_ts
frame_index
source_frame_index
det_id
class_id
class_name
conf

track_id
global_track_id
track_status

bbox_x1
bbox_y1
bbox_x2
bbox_y2
bbox_x_norm
bbox_y_norm
bbox_w_norm
bbox_h_norm

centroid_x
centroid_y
centroid_x_norm
centroid_y_norm

anchor_type
anchor_x
anchor_y
anchor_x_norm
anchor_y_norm

primary_zone_id
primary_zone_type
in_queue
queue_zone_id

model_name
detector_type
tracker_type
supervision_version
trackers_version
zone_config_version

processing_total_ms
inference_ms
tracking_ms
zone_ms
```

Partitioning:

```text
store_id
bucket(16, camera_id)
days(capture_ts)
```

## Silver Line Crossings

Add:

```text
lakehouse.rva.silver_line_crossings
```

Columns:

```text
store_id
camera_id
capture_ts
frame_index
line_id
line_type
direction
track_id
global_track_id
zone_config_version
```

This table feeds traffic and line-crossing Gold tables.

## Gold Zone Minute Metrics

Add:

```text
lakehouse.rva.gold_zone_minute_metrics
```

Columns:

```text
store_id
camera_id
zone_id
zone_type
window_start
window_end
avg_occupancy
max_occupancy
unique_visitors
detection_count
```

Use event-time tumbling windows.

## Gold Queue Sessions

Add:

```text
lakehouse.rva.gold_queue_sessions
```

Columns:

```text
store_id
camera_id
queue_zone_id
global_track_id
enter_ts
exit_ts
wait_time_sec
frame_count
completed
exit_reason
```

Queue session logic belongs in Flink keyed state:

```text
key = store_id + camera_id + queue_zone_id + global_track_id
```

Use an exit grace period to avoid splitting sessions on brief misses.

## Gold Line Crossing Counts

Add:

```text
lakehouse.rva.gold_line_crossing_counts
```

Columns:

```text
store_id
camera_id
line_id
line_type
window_start
window_end
in_count
out_count
net_count
```

This supports entrance/exit and queue entry/exit analytics.

## Gold Customer Journey

Add:

```text
lakehouse.rva.gold_customer_journey
```

Columns:

```text
store_id
camera_id
global_track_id
from_zone_id
to_zone_id
transition_ts
dwell_before_transition_sec
```

This table requires stable `global_track_id`. Do not build journey analytics
from raw tracker IDs.

## Gold Camera Health Minute

Add:

```text
lakehouse.rva.gold_camera_health_minute
```

Columns:

```text
store_id
camera_id
window_start
window_end
source_fps_avg
effective_fps_avg
dropped_frames
inference_ms_p50
inference_ms_p95
tracking_ms_p95
event_publish_failures
```

This table supports evaluation and system-health reporting.

## Validation Queries

Expected analytical questions:

```sql
-- Top crowded zones
SELECT zone_id, AVG(avg_occupancy) AS avg_occupancy
FROM lakehouse.rva.gold_zone_minute_metrics
GROUP BY zone_id
ORDER BY avg_occupancy DESC;

-- Average queue wait
SELECT queue_zone_id, AVG(wait_time_sec) AS avg_wait
FROM lakehouse.rva.gold_queue_sessions
WHERE completed = true
GROUP BY queue_zone_id;

-- Entrance traffic
SELECT line_id, SUM(in_count) AS in_total, SUM(out_count) AS out_total
FROM lakehouse.rva.gold_line_crossing_counts
GROUP BY line_id;
```

