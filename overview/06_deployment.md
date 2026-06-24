# Deployment — Cấu hình triển khai

## 1. Môi trường triển khai

| Môi trường | Máy | OS | Vai trò |
|---|---|---|---|
| Local (Edge) | Máy cá nhân | Ubuntu 22.04 + GPU | Vision Service |
| Cloud (Infra) | AWS EC2 `ip-172-31-18-183` | Ubuntu 22.04 | Toàn bộ data stack |

**EC2 specs:** ap-southeast-1 (Singapore), public IP: 52.74.215.164

## 2. Docker Compose Services (EC2)

**File:** `docker-compose.yml`

```yaml
services:
  pulsar-broker:     # Apache Pulsar 3.3.2, port 6650 (binary), 8084 (admin)
  pulsar-init:       # One-shot: tạo topics/schemas khi lần đầu khởi động
  flink-jobmanager:  # Flink 1.19, port 8081 (UI + REST)
  flink-taskmanager: # Flink worker, 4 task slots
  flink-job-submitter: # One-shot: submit tất cả Flink jobs khi stack start
  redis:             # Redis 7, port 16379 (host) → 6379 (container)
  iceberg-rest:      # Iceberg REST Catalog, port 8181
  postgres:          # PostgreSQL 15, port 5432 (INTERNAL ONLY)
  trino:             # Trino 468, port 8083
  airflow:           # Apache Airflow 2.x, port 8085
  api:               # FastAPI, port 8000 (behind nginx)
  nginx:             # Nginx, port 80 (public)
```

**Networks:** `retail-net` (bridge) — tất cả containers trong cùng network.

## 3. Environment Variables (`.env`)

File `.env` ở root project trên EC2, KHÔNG commit git:

```bash
# AWS S3
S3_ENDPOINT=https://s3.ap-southeast-1.amazonaws.com
S3_PATH_STYLE=false
S3_REGION=ap-southeast-1
S3_BUCKET=s3-retail-video-analytics
S3_ACCESS_KEY=<IAM access key>
S3_SECRET_KEY=<IAM secret key>

# Iceberg
ICEBERG_CATALOG_URI=http://iceberg-rest:8181
ICEBERG_WAREHOUSE=s3a://s3-retail-video-analytics/lakehouse

# API
CORS_ORIGINS=http://52.74.215.164

# Pulsar
PULSAR_DLQ_TOPIC=persistent://retail/metadata/dlq-events

# Redis (internal)
REDIS_HOST=redis
REDIS_PORT=6379

# PostgreSQL
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<password>
AIRFLOW_DB_NAME=airflow
ICEBERG_DB_NAME=iceberg_catalog

# Live Media
LIVE_MEDIA_TRANSPORT=redis
LIVE_MEDIA_REDIS_PREFIX=live:frame
LIVE_MEDIA_TTL_SEC=10
```

## 4. Vision Service Config (Local)

**File:** `configs/cameras.yaml`

```yaml
cameras:
  - camera_id: cam_01   # Checkout, enabled
  - camera_id: cam_02   # Aisle, enabled
  - camera_id: cam_03   # Entrance, disabled

settings:
  model_name: yolo11l.pt
  detector_imgsz: 1280
  detector_half: true            # FP16 trên GPU
  shared_inference_enabled: true

  pulsar_service_url: pulsar://52.74.215.164:6650
  live_media_transport: redis
  live_redis_host: 52.74.215.164
  live_redis_port: 16379

  s3_bucket: s3-retail-video-analytics
  s3_region: ap-southeast-1
  media_upload_enabled: true
  alert_clip_enabled: true
  alert_density_threshold: 4
  alert_cooldown_sec: 30
```

**File:** `services/vision/.env` (KHÔNG commit git):
```bash
S3_ACCESS_KEY=<IAM access key>
S3_SECRET_KEY=<IAM secret key>
S3_BUCKET=s3-retail-video-analytics
```

## 5. Flink Job Submission

**File:** `infrastructure/flink/scripts/submit-jobs.sh` (chạy qua `flink-job-submitter` container)

Sau khi stack start, job submitter tự động submit các JAR jobs:

```bash
BronzeIngestJob       → pulsar → bronze_raw
SilverJob             → bronze_raw → silver_detections_v2
RealtimeMetricsJob    → pulsar → redis
GoldTrackSummaryJob   → silver → gold_track_summary_v2
QueueAnalyticsJob     → silver → gold_queue_sessions
GoldDashboardAggJob   → silver + gold_track → gold_camera_*/gold_alert_events
GoldAlertsJob         → media-events → gold_alerts
```

**JAR:** `services/flink-jobs/java/target/rva-flink-jobs-*.jar`

## 6. Iceberg REST Catalog

**Image:** Custom Dockerfile based on `tabulario/iceberg-rest`

**Backend:** PostgreSQL (database `iceberg_catalog`, user `iceberg`)

Catalog persistence qua Postgres → data không mất khi restart (đã fix lỗi SQLite in-memory).

**DDL Gold Serving:** `services/gold_serving/sql/ddl/gold_serving.sql`
Được áp dụng qua `services/gold_serving/apply_ddl.py` khi khởi động.

## 7. Trino Configuration

**File:** `infrastructure/trino/etc/catalog/lakehouse.properties`

```properties
connector.name=iceberg
iceberg.catalog.type=rest
iceberg.rest-catalog.uri=http://iceberg-rest:8181
iceberg.rest-catalog.warehouse=s3a://s3-retail-video-analytics/lakehouse
fs.native-s3.enabled=true
s3.region=ap-southeast-1
s3.path-style-access=false
```

## 8. Airflow

**Port:** 8085 (public) → 8080 (container)

**DAGs location:** `infrastructure/airflow/dags/`

**Scheduler:** Airflow scheduler chạy theo cron, trigger refresh Gold Serving tables.

**Connection tới Trino:** qua `trino_client.py` trong `services/gold_serving/`.

**Webserver timeout fix** (đã áp dụng trong docker-compose.yml):
```yaml
AIRFLOW__WEBSERVER__WEB_SERVER_MASTER_TIMEOUT: "300"
AIRFLOW__WEBSERVER__WORKERS: "2"
```

## 9. Cách khởi động hệ thống

### EC2 (hạ tầng):
```bash
cd /home/ubuntu/retail-video-analytics
git pull origin main
docker compose up -d
# Chờ healthy: pulsar, redis, flink, trino (~3-5 phút)
```

### Local (Vision):
```bash
cd /home/hungfnguyen/project/retail-video-analytics
source .venv/bin/activate
cd services/vision
python main.py
```

### Kiểm tra:
```
http://52.74.215.164          → React Dashboard
http://52.74.215.164:8081     → Flink Web UI
http://52.74.215.164:8085     → Airflow
http://52.74.215.164:8083     → Trino (internal network only)
```

## 10. Security Notes

- **PostgreSQL 5432:** KHÔNG mở public (chỉ trong Docker network)
- **`.env` files:** KHÔNG commit vào git (covered by `.gitignore`)
- **IAM keys:** Chỉ lưu trong `.env`, không hardcode vào code
- **CORS:** Chỉ allow origin `http://52.74.215.164`
- **Trino 8083:** Không mở public cho external access (chỉ từ bên trong EC2)
