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
- centroid in pixel and normalized coordinates;
- tracker id;
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
bronze_raw payload -> ParseDetections UDTF -> silver_detections
silver_detections -> track aggregate -> gold_track_summary
```

## Current Limitations

- Historical traffic by minute/hour is not implemented yet as a Gold table.
- Historical heatmap is not implemented yet as a Gold table.
- Alert history is not implemented yet as a historical table.
- Analytics frontend currently needs API endpoints over Trino before it can show real historical data.
