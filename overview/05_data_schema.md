# Data Schema — Iceberg, Redis, Pulsar

## 1. Iceberg Tables

### Namespace `lakehouse.rva` — Bronze / Silver / Gold Facts

#### `bronze_raw`
| Column | Type | Mô tả |
|---|---|---|
| schema_version | STRING | Event schema version ("1.0") |
| event_id | STRING | Unique frame event ID |
| pipeline_run_id | STRING | Vision run ID |
| frame_index | BIGINT | Frame số trong run |
| payload | STRING | Full JSON event (raw) |
| camera_id | STRING | Camera ID |
| store_id | STRING | Store ID (partition key) |
| ingest_ts | TIMESTAMP(6) | Thời điểm Flink nhận |

Partition: `store_id`

---

#### `silver_detections_v2`
| Column | Type | Mô tả |
|---|---|---|
| schema_version | STRING | "1.0" |
| event_type | STRING | "detection_frame" |
| event_id | STRING | Frame event ID (nhiều rows cùng event_id) |
| detection_id | STRING | ID của detection trong frame |
| pipeline_run_id | STRING | Vision run ID |
| store_id | STRING | Store ID |
| camera_id | STRING | Camera ID |
| frame_index | BIGINT | Frame number |
| source_frame_index | BIGINT | Frame index từ source video |
| capture_ts | TIMESTAMP_LTZ(3) | Thời điểm frame được capture |
| img_w, img_h | INT | Kích thước ảnh |
| class_name | STRING | "person" |
| class_id | INT | 0 |
| conf | FLOAT | Detection confidence (>= 0.15) |
| track_id | INT | Track ID ổn định |
| raw_track_id | INT | Native ByteTrack ID |
| global_track_id | STRING | "cam_01_g_000042" |
| track_state | STRING | "confirmed", "lost", "predicted" |
| is_predicted | BOOLEAN | True nếu đang trong track memory |
| bbox_x1/y1/x2/y2 | FLOAT | Bounding box pixels |
| anchor_type | STRING | "bottom_center" |
| anchor_x_norm, anchor_y_norm | FLOAT | Normalized anchor [0..1] |
| primary_zone_id | STRING | Zone ID chính |
| primary_zone_type | STRING | "queue", "aisle", "dwell" |
| in_queue | BOOLEAN | Trong queue zone không |
| queue_zone_id | STRING | Queue zone ID nếu in_queue |
| model_name | STRING | "yolo11l.pt" |
| detector_type | STRING | "ultralytics_yolo" |
| tracker_type | STRING | "roboflow_bytetrack" |
| processing_ts | TIMESTAMP(6) | Flink processing time |

Partition: `store_id`, `bucket(16, camera_id)`, `days(capture_ts)`

---

#### `gold_track_summary_v2`
| Column | Type | Mô tả |
|---|---|---|
| store_id, camera_id | STRING | Dimensions |
| pipeline_run_id | STRING | Run scope |
| global_track_id | STRING | Unique person ID |
| first_seen_ts | TIMESTAMP | Lần đầu xuất hiện |
| last_seen_ts | TIMESTAMP | Lần cuối xuất hiện |
| duration_sec | DOUBLE | last_seen - first_seen |
| frame_count | BIGINT | Số frame xuất hiện |
| max_conf, avg_conf | FLOAT | Confidence |
| last_zone_id | STRING | Zone cuối cùng |
| dwell_band | STRING | "short" (<30s), "medium" (30s-5m), "long" (>5m) |

---

#### `gold_queue_sessions`
| Column | Type | Mô tả |
|---|---|---|
| store_id, camera_id | STRING | Dimensions |
| queue_zone_id | STRING | Checkout queue ID |
| global_track_id | STRING | Person ID |
| enter_ts | TIMESTAMP | Vào queue |
| exit_ts | TIMESTAMP | Ra queue |
| wait_sec | DOUBLE | Thời gian chờ (giây) |

---

#### `gold_camera_hourly_metrics` / `gold_camera_daily_metrics`
| Column | Type | Mô tả |
|---|---|---|
| store_id, camera_id | STRING | Dimensions |
| hour / date | TIMESTAMP / DATE | Granularity |
| detection_count | BIGINT | Tổng detections |
| unique_tracks | BIGINT | Unique global_track_id |
| peak_count | INT | Max count trong giờ/ngày |

---

#### `gold_alerts`
| Column | Type | Mô tả |
|---|---|---|
| alert_id | STRING | Unique alert ID |
| camera_id, store_id | STRING | Scope |
| alert_type | STRING | "density_high", "queue_overcrowded", "long_wait" |
| severity | STRING | "high", "medium", "low" |
| trigger_ts | TIMESTAMP | Thời điểm trigger |
| clip_s3_key | STRING | S3 key của video clip |
| clip_duration_sec | DOUBLE | Độ dài clip |

---

### Namespace `lakehouse.rva_gold_serving` — Gold Serving Tables

| Bảng | Grain | Nguồn | Dùng bởi |
|---|---|---|---|
| gold_serving_traffic_daily | date, camera | gold_camera_daily_metrics | Visitors trend chart |
| gold_serving_traffic_hourly | hour, camera | gold_camera_hourly_metrics | Peak hour analysis |
| gold_serving_dwell_daily | date, dwell_band | gold_track_summary_v2 | Dwell distribution |
| gold_serving_queue_daily | date, queue_zone | gold_queue_sessions | Avg wait time |
| gold_serving_queue_hourly | hour, queue_zone | gold_queue_sessions | Queue heatmap |
| gold_serving_heatmap_tile_5min | 5min, grid_cell | silver_detections_v2 | Intraday heatmap |
| gold_serving_heatmap_tile_hour | hour, grid_cell | silver_detections_v2 | Hourly heatmap |
| gold_serving_zone_daily | date, zone | silver_detections_v2 | Zone distribution |
| gold_serving_zone_hourly | hour, zone | silver_detections_v2 | Zone trend |
| gold_serving_dwell_daily | date | gold_track_summary_v2 | Dwell analytics |
| gold_serving_executive_daily | date | all Gold + serving | Executive KPIs |
| gold_serving_alert_daily | date | gold_alerts | Alert history |
| gold_serving_alert_hourly | hour | gold_alerts | Alert trend |

---

## 2. Redis Keys

### Live State (từ RealtimeMetricsJob — Flink)

| Key Pattern | Type | TTL | Nội dung |
|---|---|---|---|
| `stats:count:{camera_id}` | STRING | 30s | Số người hiện tại |
| `live:frame:{camera_id}` | STRING (JSON) | 10s | Frame metadata JSON |
| `heatmap:live:{camera_id}` | ZSET | 60s | Grid cell scores (64×48 grid) |
| `track:active:{cam}:{gid}` | HASH | 10s | bbox, zone, conf, last_seen |
| `zone:count:{camera_id}` | HASH | 10s | {zone_id: count} |
| `queue:live:{cam}:{zone}` | HASH | 30s | wait_ms, avg_wait_ms, max_wait_ms |

### Live Media (từ Vision Service)

| Key Pattern | Type | TTL | Nội dung |
|---|---|---|---|
| `live:frame:bytes:{camera_id}` | BYTES | 10s | Annotated JPEG binary |
| `live:frame:meta:{camera_id}` | STRING (JSON) | 10s | {fps, updated_at_epoch_ms, ...} |

### Alert State (từ alert_evaluator.py — FastAPI)

| Key Pattern | Type | TTL | Nội dung |
|---|---|---|---|
| `alert:live:{camera_id}` | ZSET | 24h | Alert IDs, score=timestamp, max 25 |
| `alert:item:{alert_id}` | HASH | 24h | Tất cả fields của alert |
| `alert:cooldown:{cam}:{zone}:{type}` | STRING | cooldown_sec | Chống duplicate (NX EX) |

### Analytics Cache (từ FastAPI /analytics endpoint)

| Key Pattern | Type | TTL | Nội dung |
|---|---|---|---|
| `analytics:cache:{store_id}:{days}` | STRING (JSON) | 300s | Kết quả Trino query |

---

## 3. Pulsar Topics

| Topic | Publisher | Consumer | Mô tả |
|---|---|---|---|
| `persistent://retail/metadata/events` | Vision (mỗi camera) | BronzeIngestJob, RealtimeMetricsJob | Detection frame events |
| `persistent://retail/metadata/media-events` | Vision (clip extractor) | GoldAlertsJob, API media consumer | Clip/frame upload events |
| `persistent://retail/metadata/dlq-events` | RealtimeMetricsJob | (monitoring) | Invalid events DLQ |

**Partitioning:** `events` topic có số partition = số camera enabled → events của 1 camera giữ ordering.

---

## 4. AWS S3 Structure

```
s3://s3-retail-video-analytics/
├── lakehouse/                          ← Iceberg warehouse root
│   ├── rva/                            ← namespace lakehouse.rva
│   │   ├── bronze_raw/                 ← Parquet + metadata
│   │   ├── silver_detections_v2/
│   │   ├── gold_track_summary_v2/
│   │   └── ...
│   └── rva_gold_serving/               ← namespace lakehouse.rva_gold_serving
│       ├── gold_serving_traffic_daily/
│       └── ...
├── frames/                             ← Sampled frame JPEGs (optional)
│   └── {date}/{store_id}/{cam}/{hour}h/{timestamp}_{frame}.jpg
├── clips/                              ← Alert video clips
│   └── {date}/{store_id}/{cam}/{alert_id}.mp4
└── snapshots/                          ← Alert snapshot JPEGs
    └── {cam}/{alert_id}.jpg
```
