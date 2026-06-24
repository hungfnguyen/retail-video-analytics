# Kiến Trúc Hệ Thống

## 1. Luồng dữ liệu tổng quan

```
Video Files / Cameras
        │
        ▼
┌───────────────────┐
│   Vision Service  │  ← Python, YOLO11l, ByteTrack
│   (Local GPU)     │
└───────┬───────────┘
        │ Detection Frame Events (JSON)
        ▼
┌───────────────────┐
│  Apache Pulsar    │  ← Message broker, persistent topics
│  (EC2 :6650)      │
└───────┬───────────┘
        │
   ┌────┴─────────┐
   │              │
   ▼              ▼
[Lakehouse     [Realtime
 Path]          Path]
   │              │
   ▼              ▼
Apache Flink   Apache Flink
Table API      DataStream
Jobs (Java)    Job (Java)
   │              │
   ▼              ▼
Apache Iceberg  Redis 7
(S3 Warehouse)  (Live State)
   │              │
   ▼              └────────┐
Trino 468                  │
(SQL Engine)               │
   │                       │
   └──────────┬────────────┘
              ▼
         FastAPI
         (Python)
              │
              ▼
      React Dashboard
      (TypeScript)
```

## 2. Dual-Path Design

Thiết kế hai luồng tách biệt là điểm cốt lõi của kiến trúc:

### 2.1 Realtime Path (Độ trễ thấp)

```
Pulsar ──▶ RealtimeMetricsJob ──▶ Redis ──▶ FastAPI /api/v1/live/{cam}/dashboard ──▶ React Live Page
```

**Mục đích:** Hiển thị real-time — số người hiện tại, heatmap, track active, alert mới nhất.

**Redis keys được ghi:**
```
stats:count:{camera_id}              INT — số người hiện tại, TTL ngắn
live:frame:{camera_id}               JSON — frame metadata mới nhất
heatmap:live:{camera_id}             ZSET — điểm nhiệt trên lưới 64×48
track:active:{camera_id}:{track_id}  HASH — bbox, zone, confidence
zone:count:{camera_id}               HASH — số người theo từng zone
queue:live:{camera_id}:{zone_id}     HASH — wait_ms, max_wait_ms cho queue zone
alert:live:{camera_id}               ZSET — alert IDs theo timestamp
alert:item:{alert_id}                HASH — chi tiết alert
alert:cooldown:{cam}:{zone}:{type}   STRING — chống spam alert, TTL = cooldown_sec
live:frame:bytes:{camera_id}         BYTES — JPEG frame annotated, TTL ngắn
live:frame:meta:{camera_id}          JSON — metadata của JPEG frame
```

### 2.2 Lakehouse Path (Độ chính xác cao)

```
Pulsar ──▶ BronzeIngestJob ──▶ bronze_raw (Iceberg)
                                    │
                          SilverJob ▼
                          silver_detections_v2 (Iceberg)
                                    │
              ┌─────────────────────┼──────────────────────┐
              ▼                     ▼                       ▼
  GoldTrackSummaryJob     QueueAnalyticsJob     GoldDashboardAggregateJob
  gold_track_summary_v2   gold_queue_sessions   gold_camera_hourly_metrics
                                                gold_camera_daily_metrics
                                                gold_camera_daily_dwell
                                                gold_alert_events
                                    │
              GoldAlertsJob ────────┘
              gold_alerts (từ media-events)
                                    │
                        Airflow DAGs (Trino SQL)
                                    │
                          gold_serving_* (Iceberg)
                                    │
                             Trino ─┘
                                    │
                    FastAPI /api/v1/analytics/dashboard
                                    │
                         React Analytics Page
```

**Mục đích:** Phân tích lịch sử, audit, drill-down.

## 3. Medallion Architecture

```
Bronze (Raw)    → silver_detections_v2 (Enriched) → Gold Facts → Gold Serving
bronze_raw         1 row / person / frame             Summary       Query-ready
payload JSON       flatten + enrich + validate        aggregates    for dashboard
  ~72K events      ~363K rows                         ~5.8K tracks  12 tables
```

**Nguyên tắc:**
- **Bronze**: giữ nguyên raw JSON payload, không transform — dùng để replay và audit
- **Silver**: flatten thành detection rows, áp dụng quality rules (dedup, conf >= 0.15, non-null IDs)
- **Gold Facts**: aggregate theo business grain (track lifecycle, queue session, daily metrics)
- **Gold Serving**: denormalized, query-ready, refresh theo Airflow schedule

## 4. Alert Pipeline

Có hai loại alert độc lập:

### Alert từ API Background Evaluator (runtime, mỗi 10 giây)
```
Redis queue:live + zone:count ──▶ alert_evaluator.py ──▶ alert:live:{cam} (Redis)
```
Loại: `queue_overcrowded` (≥5 người), `long_wait` (max_wait > 2 phút), `pipeline_lag` (frame > 15s tuổi)

### Alert từ Vision Clip Extractor (density-based)
```
Vision (density > threshold) ──▶ clip_extractor.py ──▶ S3 clip ──▶ Pulsar media-events
──▶ API _media_consumer_loop ──▶ alert:live:{cam} (Redis)
```
Loại: `density_high`

### Alert lịch sử (Iceberg)
```
Flink GoldAlertsJob ──▶ gold_alerts (Iceberg) ──▶ Airflow ──▶ gold_serving_alert_* ──▶ API analytics
```

## 5. Component Phụ Trách

| Component | Language | Chạy ở đâu | Vai trò |
|---|---|---|---|
| `services/vision/` | Python 3.11 | Local GPU | CV pipeline, phát hiện, tracking, publish event |
| `services/flink-jobs/java/` | Java 17 + Flink 1.19 | EC2 (Docker) | 9 Flink jobs xử lý stream |
| `services/api/` | Python + FastAPI | EC2 (Docker) | REST API, alert evaluator |
| `services/gold_serving/` | Python + Trino SQL | EC2 (Docker via Airflow) | Refresh serving tables |
| `frontend/` | React 18 + TypeScript | EC2 (Nginx static) | Dashboard UI |
| `infrastructure/airflow/dags/` | Python (Airflow) | EC2 (Docker) | Orchestrate Gold Serving refresh |
| `packages/core/` | Python | Shared | Models, constants, settings |
| `packages/messaging/` | Python | Shared | Pulsar client wrapper |
| `packages/storage/` | Python | Shared | Redis, S3 client wrappers |
