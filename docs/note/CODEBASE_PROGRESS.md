# Codebase Progress Report — 2026-05-19

> Trạng thái hiện tại của retail-video-analytics sau khi hoàn thành M0-M4.
> Tài liệu này để onboarding session chat agent mới hiểu context dự án.

---

## 1. Project Overview

**Đồ án tốt nghiệp Data Engineering**: Hệ thống realtime pipeline thu thập & xử lý metadata video camera siêu thị.

**Stack**: YOLO11 + BoTSORT → Pulsar → Flink (dual-path) → Redis + Iceberg/MinIO → Trino → Grafana

**Monorepo**: Python uv workspace (`services/vision`, `packages/core`, `packages/messaging`, `packages/storage`) + Java Maven (`services/flink-jobs/java`)

**Branch**: `feat/flink-processing`

---

## 2. Completed Components

### 2.1 Shared Python Packages (M0-M1) — COMPLETE

| Package | Files | Lines | Status |
|---------|-------|-------|--------|
| `packages/core/` | 5 files | 380 | Pydantic models, constants, settings, time_utils |
| `packages/messaging/` | 2 files | 108 | PulsarProducer, PulsarConsumer |
| `packages/storage/` | 3 files | 111 | S3ClientConfig, create_s3_client, RedisClientConfig, create_redis_client |

**Key models**: `DetectionFrameEvent` (có `event_id` auto-generate SHA256[:16]), `DetectionObject`, `Source`, `BBox`, `Centroid`, `Runtime`, `SampledFrameResult`, `ClipCreatedResult`, `TrackLifecycleEvent`, `AlertEvent`

**Dead code trong packages**:
- `PulsarProducer` / `PulsarConsumer` — KHÔNG AI DÙNG. Vision dùng `PulsarEmitter` riêng
- `RedisClientConfig` / `create_redis_client` — KHÔNG AI DÙNG. Flink dùng Jedis (Java), Vision không cần Redis
- `AlertEvent`, `TrackLifecycleEvent` — model được định nghĩa nhưng chưa emit ở đâu
- `TOPIC_ALERTS`, `TOPIC_TRACK_LIFECYCLE`, `TOPIC_SYSTEM_METRICS` — constants được định nghĩa nhưng chưa dùng

### 2.2 Vision Service (M2) — COMPLETE

| File | Lines | Vai trò |
|------|-------|--------|
| `main.py` | 110 | CameraManager: multiprocessing, health check, restart backoff |
| `worker.py` | 265 | Pipeline loop: read → detect → track → publish |
| `reader.py` | 98 | VideoFileReader: thread, queue.Queue, realtime FPS, loop |
| `config/settings.py` | 225 | load_cameras_config() từ YAML + env |
| `emit/pulsar_emitter.py` | 234 | PulsarEmitter: validate DetectionFrameEvent, retry, partition_key=camera_id |
| `emit/frame_sampler.py` | 183 | JPEG upload S3 1fps, ThreadPoolExecutor |
| `emit/clip_extractor.py` | 252 | Alert MP4 clip, ring buffer, disabled by default |
| `detect/yolo_detector.py` | 64 | YoloDetector (chỉ DeepSORT dùng) |
| `track/` | 6 files | BoTSORT, ByteTrack, DeepSORT |
| `utils/` | 2 files | path_utils, visualizer (dead code) |

**Kiến trúc**: 1 camera = 1 Process = 1 PulsarClient. BoTSORT/ByteTrack dùng Ultralytics `model.track(persist=True)` trực tiếp.

**Config**: `configs/cameras.yaml` — 2 camera (cam_01, cam_02), model `yolo11n.pt`, tracker `botsort`, class_filter `[0]`, FPS target 25.

### 2.3 Flink Java Jobs (M3-M4) — COMPLETE

| Job | API | Source | Sink | Checkpoint | Lines |
|-----|-----|--------|------|------------|-------|
| `BronzeIngestJob` | Table API/SQL | Pulsar events (raw) | Iceberg bronze_raw | 60s | 113 |
| `SilverJob` | Table API/SQL | Iceberg bronze_raw | Iceberg silver_detections | 30s | 172 |
| `GoldTrackSummaryJob` | Table API/SQL | Iceberg silver_detections | Iceberg gold_track_summary (upsert) | 30s | 115 |
| `RealtimeMetricsJob` | **DataStream API** | Pulsar events (raw) | Redis + DLQ PulsarSink | **10s** | 348 |

**4 jobs compiled vào 1 JAR** (`silver-job-0.1.0.jar`), Dockerfile copy thành 5 tên, submit-jobs.sh dùng `-c` flag chọn class.

**Dual-path**:
- Lakehouse: Pulsar → Bronze → Iceberg bronze_raw → Silver → Iceberg silver_detections → Gold → Iceberg gold_track_summary → Trino → Grafana (latency 2-3 min)
- Realtime: Pulsar → RealtimeMetricsJob → Redis (live_count, heatmap, active_tracks) + DLQ Pulsar topic (latency <5s)

**event_id**: Được extract trong Bronze SQL (`JSON_VALUE`), propagate trong Silver (`COALESCE`), dùng làm dedup key trong RealtimeMetricsJob (ValueState TTL 10min)

**DLQ**: Chỉ RealtimeMetricsJob có DLQ thật (PulsarSink → `persistent://retail/metadata/dlq-events`). ParseDetections UDTF catch exception + log + counter, không side-output.

### 2.4 Infrastructure — COMPLETE

**docker-compose.yml**: 12 services
- pulsar-broker (256m heap + 256m direct)
- pulsar-init (init topics + schema, exit 0)
- flink-jobmanager (800m)
- flink-taskmanager (1600m, 8 slots)
- flink-job-submitter (submit 4 jobs, exit 0)
- redis:7-alpine
- minio (S3-compatible)
- mc + minio-init (create buckets)
- iceberg-rest:0.7.0
- trino:418
- grafana:11.3.0

**Pulsar topics** (tenant: retail, namespace: retail/metadata):
| Topic | Partitions | Schema |
|-------|-----------|--------|
| `events` | 2 (env PULSAR_EVENTS_PARTITIONS) | Avro record (DetectionFrameEvent), BACKWARD, validation DISABLED |
| `media-events` | 1 | None |
| `dlq-events` | 1 | None |

**Flink config**: cluster default checkpoint 30s, parallelism.default 2, RocksDB state backend

**Pulsar subscriptions**:
- `flink-bronze-java-sub` (start: earliest)
- `flink-realtime-sub` (start: latest)

### 2.5 Tests — COMPLETE

51 tests pass, lint sạch.
- `tests/unit/test_models.py` (12 tests) — event_id, BBox, serialization
- `tests/unit/test_constants.py` (7 tests) — topic format, defaults
- `tests/unit/test_settings.py` (17 tests) — env override, type coercion
- `tests/unit/test_time_utils.py` (5 tests) — UTC conversion
- `tests/integration/test_s3_client_config.py` (4 tests) — config validation

**Coverage gaps**: Không có test cho vision service (worker, reader, emitter, trackers), không có E2E test.

### 2.6 Documentation — COMPLETE

14 docs từ 00 đến 13 + README + 10 mermaid diagrams.
- `docs/mermaid/01_vison/` — 6 diagrams về vision architecture
- `docs/mermaid/02_pulsar/` — 2 diagrams về Pulsar flow & architecture
- `docs/mermaid/03_flink/` — 1 diagram về Flink architecture trong RVA

---

## 3. Verified Runtime Status

**Lần chạy cuối (2026-05-19)**:
- Tất cả 12 container healthy hoặc exited (0)
- pulsar-init: exit 0, 3 topics created
- flink-job-submitter: exit 0, 4 jobs submitted
- 4 Flink jobs: RUNNING (sau khi fix slots 2→8)
- Pulsar schema: upload thành công, 10 fields Avro record
- Redis: ping PONG
- Logs: ghi ra `./logs/pulsar/`, `./logs/flink/`, `./logs/trino/`, `./logs/grafana/`

**Vấn đề đã gặp & fix**:
1. Pulsar schema upload HTTP 422 → fix: schema file sai format (object thay vì string), generate bằng Python
2. Flink jobs RESTARTING (NoResourceAvailableException) → fix: `taskmanager.numberOfTaskSlots: 2 → 8`
3. Pulsar broker crash (Permission denied log dir) → fix: mount log volume + chmod 777
4. RAM laptop không đủ (14GB Docker) → fix: JM 800m, TM 1600m, Pulsar 256m+256m

---

## 4. Not Yet Implemented (Roadmap M5-M8)

| Component | Doc Reference | Trạng thái |
|-----------|--------------|-----------|
| **FastAPI serving** | docs/07, roadmap M5 | `services/api/` rỗng |
| **Streamlit dashboard** | docs/07, roadmap M6 | `services/streamlit/` rỗng |
| **PostgreSQL operational DB** | docs/05 | Không có trong docker-compose |
| **Gold minute/hour/day metrics** | docs/04 | Chỉ có `gold_track_summary` |
| **Alert generation (sliding window)** | docs/03 section 7.4 | Chưa implement |
| **Evaluation/benchmark** | docs/09, roadmap M8 | Chưa có scripts |
| **Schema validation enforced** | Phase 2 plan | Đang disabled |
| **Vision producer schema-aware** | Phase 2 plan | Đang raw bytes |
| **E2E tests** | tests/e2e/ | Rỗng |

---

## 5. Key Architectural Decisions

| Quyết định | Lý do |
|------------|-------|
| Dual-path (Lakehouse + Realtime) | Lakehouse cho historical analytics, Realtime cho live dashboard <5s |
| Table API cho lakehouse, DataStream cho realtime | Iceberg native integration vs custom Redis sink + DLQ side-output |
| 1 camera = 1 Process = 1 PulsarClient | Multiprocessing isolation, không share được Pulsar client qua process |
| partition_key=camera_id, events=2 partitions | Ordering per camera, hash(camera_id) % partitions |
| event_id = SHA256(camera_id|capture_ts|frame_index)[:16] | Deterministic, idempotent khi replay |
| Schema registered but validation disabled | Producer còn raw bytes, chưa schema-aware |
| PulsarEmitter giữ trong vision (không dùng shared PulsarProducer) | Vision-specific: validate model, dual topic, media event |
| Single JAR, multiple entry points | Đơn giản build, submit-jobs.sh chọn class |
| Bronze đọc earliest, Realtime đọc latest | Lakehouse cần toàn bộ lịch sử, Realtime chỉ cần event mới |

---

## 6. File Count Summary

| Layer | Files | Total Lines |
|-------|-------|-------------|
| Python packages (core/messaging/storage) | 10 .py | 630 |
| Vision service | 23 .py | 1,878 |
| Java Flink jobs | 5 .java | 878 |
| Tests | 5 .py | 374 |
| Infrastructure config | 15 files | — |
| Documentation | 14 docs + 10 mermaid | — |
| **Tổng** | ~67 files | ~3,760 lines |

---

## 7. Quick Commands Reference

```bash
# Start infrastructure
docker compose up -d --build

# Check all services
docker compose ps

# Flink UI
open http://localhost:8081

# Verify 4 Flink jobs
curl -s http://localhost:8081/jobs/overview | python3 -m json.tool | grep state

# Pulsar topics
docker exec pulsar-broker bin/pulsar-admin topics list retail/metadata

# Pulsar schema
docker exec pulsar-broker bin/pulsar-admin schemas get persistent://retail/metadata/events

# Redis live data
docker exec redis redis-cli KEYS "*"

# Run Vision
uv run --package rva-vision python services/vision/main.py

# Tests & lint
make test
make lint

# Logs snapshot
./scripts/snapshot-logs.sh
./scripts/tail-logs.sh

# Reset
docker compose down -v && docker compose up -d --build
```
