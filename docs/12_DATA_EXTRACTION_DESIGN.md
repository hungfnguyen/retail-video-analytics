# Data Extraction Design

## Principle

The analytical data product is not raw video. The system extracts structured frame-level and object-level metadata, then stores that metadata for realtime serving and historical analytics.

## From Frame To Event

```text
Frame
  -> YOLO detection
  -> tracker id assignment
  -> bbox + centroid normalization
  -> DetectionFrameEvent JSON
  -> Pulsar
```

Each event contains:

- source store/camera metadata;
- frame index and capture timestamp;
- image size;
- detection list;
- bbox in pixel and normalized coordinates;
- centroid/anchor in pixel and normalized coordinates;
- raw track id, stabilized track id, and global track id;
- zone and queue assignment;
- runtime metadata.

## Why Normalize Coordinates

Normalized bbox and centroid fields allow downstream consumers to map detections onto any display resolution or heatmap grid.

```text
grid_x = floor(centroid_norm.x * 64)
grid_y = floor(centroid_norm.y * 48)
```

Realtime Redis heatmap uses this grid mapping.

## Media Extraction

Media artifacts are separate from analytical metadata.

| Artifact | Path | Purpose |
|---|---|---|
| Latest annotated JPEG | `runtime/live_frames/` | Current dashboard video |
| Sampled JPEG | AWS S3 `frames/` | Investigation sample |
| Optional clip | AWS S3 `clips/` | Incident replay artifact |

## Current Lakehouse Extraction

```text
Pulsar raw JSON -> bronze_raw
bronze_raw payload -> ParseDetections UDTF -> silver_detections_v2
silver_detections_v2 -> track aggregate -> gold_track_summary_v2
silver_detections_v2 -> queue aggregate -> gold_queue_sessions_v2
media-events -> clip incident aggregate -> gold_alerts
Gold facts / Silver -> Gold serving -> rva_gold_serving.gold_serving_*
```

## Current Limitations

- Airflow is present as an orchestration skeleton, not yet a fully wired runtime service in compose.
- Some Gold serving tables are currently refreshed by Trino SQL runners; they may move to Flink batch only if measured complexity justifies it.
- Line-crossing/funnel historical tables are not yet modeled as lakehouse products.
