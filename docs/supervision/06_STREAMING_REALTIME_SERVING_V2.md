# Streaming Realtime Serving V2

## Goal

Extend the realtime path so richer Vision facts are available to the Live
dashboard without changing the core architecture:

```text
Pulsar -> Flink realtime -> Redis TTL state -> FastAPI -> React
```

Vision does not write Redis directly.

## Realtime Job V2

Current realtime job:

```text
Pulsar raw JSON
  -> parse/validate
  -> deduplicate by event_id
  -> Redis count/frame/heatmap/tracks
  -> DLQ invalid events
```

V2 realtime job:

```text
Pulsar v1/v2 raw JSON
  -> ParseValidateV2
  -> Deduplicate by event_id
  -> Extract detections
  -> Update active tracks by global_track_id
  -> Update zone counts
  -> Update queue live metrics
  -> Update line counters
  -> Redis sink
  -> DLQ invalid events
```

The parser should support both schema versions during migration.

## Existing Redis Keys

Keep existing keys:

```text
stats:count:{camera_id}
live:frame:{camera_id}
heatmap:live:{camera_id}
```

These keep current FastAPI/React compatibility.

## Active Track Key

Move active tracks toward `global_track_id`:

```text
track:active:{camera_id}:{global_track_id}
```

Hash fields:

```text
track_id
global_track_id
last_seen_ts
current_zone_id
anchor_x_norm
anchor_y_norm
bbox_x
bbox_y
bbox_w
bbox_h
conf
track_age_sec
zone_enter_ts
quality_flags
```

TTL:

```text
30 seconds baseline
```

During migration, the job may also write the old
`track:active:{camera_id}:{track_id}` key if the API still depends on it.

## Zone Count Key

```text
zone:count:{camera_id}
```

Redis hash:

```text
HSET zone:count:cam_01 checkout_queue_01 3 promo_area_01 1 entrance_area 2
EXPIRE zone:count:cam_01 10
```

Use frame-level `zone_counts` from Vision, not Redis-side geometry.

## Queue Live Key

```text
queue:live:{camera_id}:{zone_id}
```

Redis hash:

```text
current_count
oldest_wait_sec
avg_wait_sec
max_wait_sec
threshold_status
oldest_global_track_id
last_update_ts
```

Queue wait values should come from Flink state, not Vision-only memory, once
QueueSessionJob is implemented.

Before QueueSessionJob exists, the realtime job may write only `current_count`
and `last_update_ts`.

## Line Count Key

```text
line:count:{camera_id}:{line_id}:{window}
```

Example fields:

```text
in_count
out_count
net_count
window_start
last_update_ts
```

Use short windows for Live UI, such as `5m`.

## TTL Policy

All live keys must expire.

Recommended TTLs:

```text
stats:count                 5 seconds
live:frame                  10 seconds
zone:count                  10 seconds
queue:live                  10 seconds
track:active                30 seconds
line:count short window     10-60 seconds depending on window policy
```

This preserves current behavior where dashboard freshness degrades when Vision,
Flink, or Redis stops updating.

## FastAPI Impact

Extend the existing live endpoint response with:

```text
zones[]
queues[]
lines[]
tracks[] by global_track_id
vision quality metrics
```

Keep existing fields for:

```text
frame
stats
heatmap_points
zone_heatmap
pipeline_health
```

This lets the frontend migrate gradually.

## React Live Impact

Add Live UI elements:

- semantic zone occupancy cards;
- checkout queue length;
- oldest queue wait;
- entrance in/out counters;
- active global tracks;
- low FPS / high drop / high ID-switch warning.

The media stream still comes from FastAPI media endpoints. Redis does not store
video bytes.

## Failure Handling

Invalid v2 events go to DLQ.

If optional v2 fields are missing:

- fallback to v1 count and frame metadata;
- skip zone/queue/line writes for that event;
- log structured warnings in Flink metrics.

If Redis write fails:

- log error;
- rely on retries/checkpoint semantics where available;
- keep Iceberg lakehouse path independent.

