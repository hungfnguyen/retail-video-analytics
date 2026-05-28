# S3 Infrastructure Design

## 1. Bucket & naming convention

| Item | Name | Rationale |
|------|------|-----------|
| **Bucket** | `retail-video-analytics` | Project name, no abbreviation, readable |
| **Region** | `ap-southeast-1` (Singapore) | Gần VN, latency thấp cho demo |
| **Storage class** | Standard (default) | Demo nhỏ, không cần tiering |

```
s3://retail-video-analytics/
```

> Trong demo local: AWS S3 bucket `warehouse` giữ nguyên trong Docker Compose. Cấu trúc bên trong bucket giống hệt production S3 để đảm bảo tính nhất quán khi migrate.

## 2. S3 top-level layout

```
s3://retail-video-analytics/
├── lakehouse/                    # Iceberg warehouse root
│   └── retail.db/                # Database directory (Iceberg-managed)
│       ├── bronze_detection_frames/
│       ├── silver_detections/
│       ├── silver_track_lifecycle/
│       ├── silver_camera_frame_metrics/
│       ├── gold_camera_minute_metrics/
│       ├── gold_camera_hourly_heatmap/
│       └── gold_store_daily_metrics/
│
├── frames/                       # Sampled JPEG frames (1fps)
│   └── {event_date}/
│       └── {store_id}/
│           └── {camera_id}/
│               └── {hour}/
│                   └── {HH-mm-ss}_{frame_index:09d}.jpg
│
├── clips/                        # Alert video clips
│   └── {event_date}/
│       └── {store_id}/
│           └── {camera_id}/
│               └── {alert_id}.mp4
│
├── checkpoints/                  # Flink checkpoint storage
│   ├── bronze-ingest/
│   ├── realtime-metrics/
│   ├── silver-curation/
│   └── gold-aggregation/
│
├── savepoints/                   # Flink savepoints (manual)
│   └── {job_name}/
│       └── savepoint-{timestamp}/
│
└── artifacts/                    # ML models & configs (optional)
    └── models/
        └── {model_name}/
            └── {version}/
                └── model.pt
```

## 3. Iceberg namespace hierarchy

Catalog → Schema → Table (3-level như database tiêu chuẩn):

```
CATALOG: lakehouse
├── SCHEMA: retail
│   ├── bronze_detection_frames        (raw detection frame events)
│   ├── silver_detections              (flattened detection objects)
│   ├── silver_track_lifecycle         (track start/sample/end)
│   ├── silver_camera_frame_metrics    (per-frame aggregate metrics)
│   ├── gold_camera_minute_metrics     (minute-level aggregates)
│   ├── gold_camera_hourly_heatmap     (hourly sparse heatmap)
│   └── gold_store_daily_metrics       (daily store KPIs)
│
└── SCHEMA: quality
    └── pipeline_quality_daily         (data quality report)
```

Full qualified table names:

| Table | FQN |
|-------|-----|
| Bronze | `lakehouse.retail.bronze_detection_frames` |
| Silver — Detections | `lakehouse.retail.silver_detections` |
| Silver — Track | `lakehouse.retail.silver_track_lifecycle` |
| Silver — Frame | `lakehouse.retail.silver_camera_frame_metrics` |
| Gold — Minute | `lakehouse.retail.gold_camera_minute_metrics` |
| Gold — Heatmap | `lakehouse.retail.gold_camera_hourly_heatmap` |
| Gold — Daily | `lakehouse.retail.gold_store_daily_metrics` |
| Quality | `lakehouse.quality.pipeline_quality_daily` |

## 4. Partitioning strategy

| Table | Partition columns | Pattern |
|-------|------------------|---------|
| `bronze_detection_frames` | `event_date`, `store_id`, `camera_id` | Hive: `event_date=YYYY-MM-DD/store_id=.../camera_id=.../` |
| `silver_detections` | `event_date`, `store_id`, `bucket(16, camera_id)` | Hidden partitioning via Iceberg |
| `silver_track_lifecycle` | `event_date`, `store_id`, `camera_id` | |
| `silver_camera_frame_metrics` | `event_date`, `store_id`, `camera_id` | |
| `gold_camera_minute_metrics` | `event_date`, `store_id` | |
| `gold_camera_hourly_heatmap` | `event_date`, `store_id`, `camera_id` | |
| `gold_store_daily_metrics` | `date`, `store_id` | |
| `quality_pipeline_quality_daily` | `date` | |

## 5. Frame object path convention

```
s3://retail-video-analytics/frames/2026-05-07/store_001/cam_01/10/10-30-00_00001502.jpg
                   │        │         │          │       │   │        │        │
                   │        │         │          │       │   │        │        └─ frame_index (9-digit zero-padded)
                   │        │         │          │       │   │        └─ timestamp (HH-mm-ss)
                   │        │         │          │       │   └─ hour (24h)
                   │        │         │          │       └─ camera_id
                   │        │         │          └─ store_id
                   │        │         └─ event_date (ISO-8601)
                   │        └─ frames prefix
                   └─ bucket
```

## 6. Alert clip path convention

```
s3://retail-video-analytics/clips/2026-05-07/store_001/cam_01/alert-cam_01-20260507T103005Z-density.mp4
                   │     │         │          │       │        │
                   │     │         │          │       │        └─ alert_id + .mp4
                   │     │         │          │       └─ camera_id
                   │     │         │          └─ store_id
                   │     │         └─ event_date
                   │     └─ clips prefix
                   └─ bucket
```

## 7. Env vars cho S3

```bash
# .env (production S3)
S3_ENDPOINT=https://s3.ap-southeast-1.amazonaws.com
S3_REGION=ap-southeast-1
S3_BUCKET=retail-video-analytics
S3_ACCESS_KEY=<your-access-key>
S3_SECRET_KEY=<your-secret-key>

# Iceberg warehouse
ICEBERG_WAREHOUSE=s3://retail-video-analytics/lakehouse

# Cho local demo (AWS S3)
S3_ENDPOINT=https://s3.ap-southeast-2.amazonaws.com
S3_REGION=us-east-1
S3_BUCKET=warehouse
S3_ACCESS_KEY=CHANGE_ME
S3_SECRET_KEY=CHANGE_ME
ICEBERG_WAREHOUSE=s3://warehouse/lakehouse
```

## 8. Lifecycle & retention

| Object class | Retention | Storage class | Rationale |
|-------------|-----------|---------------|-----------|
| Iceberg data files | Indefinite (demo) / 90 days (prod) | Standard | Analytical data |
| Iceberg snapshots | 7 days | Standard | Time travel window |
| Sampled frames | 7 days | Standard → IA sau 3 ngày | Chỉ để investigation |
| Alert clips | 30 days | Standard | Retention ngắn hơn frames |
| Flink checkpoints | Auto-clean sau cancel | Standard | DELETE_ON_CANCELLATION |
| Flink savepoints | 30 days | Standard | Manual save before upgrade |

## 9. Access control (production direction)

| Principal | Bucket path | Permission | Purpose |
|-----------|------------|------------|---------|
| Vision service | `frames/*` | `s3:PutObject` | Upload sampled frames |
| Vision service | `clips/*` | `s3:PutObject` | Upload alert clips |
| Flink JobManager | `checkpoints/*`, `savepoints/*` | `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` | Checkpointing |
| Flink TaskManager | `lakehouse/*` | `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` | Iceberg write |
| Trino | `lakehouse/*` | `s3:GetObject`, `s3:ListBucket` | Query |
| FastAPI | `frames/*`, `clips/*` | `s3:GetObject` | Signed URL generation |
| Admin | `*` | Full access | Maintenance |

> Trong demo local, AWS S3 dùng 1 access key duy nhất cho toàn bộ service.

## 10. Migration path: local → production

```
Local demo (Docker Compose)              Production (AWS)
─────────────────────────────────        ─────────────────────────
AWS S3: s3:9000                  →      S3: s3.ap-southeast-1.amazonaws.com
Bucket: warehouse                  →      Bucket: retail-video-analytics
Path style: true                   →      Path style: false (virtual-hosted)
Auth: static access key            →      Auth: IAM role hoặc access key
ICEBERG_WAREHOUSE=s3://warehouse   →      ICEBERG_WAREHOUSE=s3://retail-video-analytics/lakehouse
```

**Chỉ cần đổi 4 biến env** để migrate, không cần sửa code:
```bash
S3_ENDPOINT, S3_REGION, S3_BUCKET, ICEBERG_WAREHOUSE
```
