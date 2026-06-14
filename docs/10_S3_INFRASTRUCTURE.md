# AWS S3 Infrastructure

## Current Bucket

| Item | Value |
|---|---|
| Bucket | `retail-video-analytics-prod` |
| Region | `ap-southeast-2` |
| Path style | `false` |
| Endpoint | `https://s3.ap-southeast-2.amazonaws.com` |

## Top-Level Layout

```text
s3://retail-video-analytics-prod/
├── lakehouse/       Iceberg warehouse root
├── frames/          optional sampled JPEG frames
└── clips/           optional alert clips
```

Flink checkpoint/savepoint storage currently uses Docker/Flink state configuration, not an S3 checkpoint prefix in the default compose file.

## Iceberg Warehouse

The configured warehouse is:

```text
s3a://retail-video-analytics-prod/lakehouse
```

The Java jobs and Trino append `/iceberg` when creating or reading the Iceberg REST catalog warehouse, so physical Iceberg table objects are under the warehouse-managed prefix.

Current logical tables:

```text
lakehouse.rva.bronze_raw
lakehouse.rva.silver_detections_v2
lakehouse.rva.gold_track_summary_v2
lakehouse.rva.gold_queue_sessions
lakehouse.rva.gold_camera_hourly_metrics
lakehouse.rva.gold_camera_daily_metrics
lakehouse.rva.gold_camera_daily_dwell
lakehouse.rva.gold_alert_events
lakehouse.rva.gold_alerts
lakehouse.rva_gold_serving.gold_serving_*
```

## Media Object Paths

Sampled frames:

```text
frames/{YYYY-MM-DD}/{store_id}/{camera_id}/{HH}h/{HHMMSS}_{frame_index:09d}.jpg
```

Optional alert clips:

```text
clips/{YYYY-MM-DD}/{store_id}/{camera_id}/{alert_id}.mp4
```

## Environment Variables

```env
S3_ENDPOINT=https://s3.ap-southeast-2.amazonaws.com
S3_PATH_STYLE=false
S3_REGION=ap-southeast-2
S3_ACCESS_KEY=CHANGE_ME
S3_SECRET_KEY=CHANGE_ME
ICEBERG_WAREHOUSE=s3a://retail-video-analytics-prod/lakehouse
```

The same values must be available to:

- Flink JobManager;
- Flink TaskManager;
- Flink job submitter;
- Iceberg REST;
- Trino;
- host-side Vision service for sampled media uploads.

## Minimal IAM Policy

For local development with one IAM user, use bucket-scoped access:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::retail-video-analytics-prod"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::retail-video-analytics-prod/*"
    }
  ]
}
```

Add `s3:ListAllMyBuckets` only if the user must run plain `aws s3 ls` without a bucket path.

## Verification

```bash
aws s3 ls s3://retail-video-analytics-prod/
aws s3 ls s3://retail-video-analytics-prod/lakehouse/ --recursive | head
aws s3 ls s3://retail-video-analytics-prod/frames/ --recursive | head
```
