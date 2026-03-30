# Camera Processing Architecture

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current vs Proposed Architecture](#2-current-vs-proposed-architecture)
3. [Component Design](#3-component-design)
4. [Data Flow Diagram](#4-data-flow-diagram)
5. [Bottleneck Analysis & Prevention](#5-bottleneck-analysis--prevention)
6. [Resource Estimation](#6-resource-estimation)
7. [Deployment Architecture](#7-deployment-architecture)
8. [Configuration Management](#8-configuration-management)
9. [Failure Handling & Recovery](#9-failure-handling--recovery)
10. [Scalability Considerations](#10-scalability-considerations)
11. [Testing Strategy](#11-testing-strategy)
12. [Implementation Roadmap](#12-implementation-roadmap)

---

## 1. Executive Summary

The camera processing subsystem handles real-time ingestion of video streams from multiple IP cameras, performs people detection and tracking, and publishes results to downstream services.

**Goals:**
- **Multi-camera**: Support 4–8 simultaneous cameras on a single GCP VM
- **Low-latency**: Detection metadata delivered to Pulsar within 100ms of capture
- **Fault-tolerant**: Individual camera failures do not affect other cameras; auto-recovery without manual intervention

**Approach:** One OS process per camera. Each process runs an RTSP reader thread, YOLO11 GPU inference, BoTSORT tracking, and a detection publisher. A supervisor process (CameraManager) monitors and restarts failed workers.

---

## 2. Current vs Proposed Architecture

### 2.1 Current Architecture — Problems

| Problem | Impact |
|---------|--------|
| Single camera only (`VIDEO_PATH` env var) | Cannot scale to multi-camera |
| No reconnect logic | Camera disconnect = process exit |
| All components in one thread | Python GIL blocks concurrent I/O and inference |
| OpenCV reads frames blocking | Frames accumulate in buffer, introduces lag |
| No process isolation | One crash takes down the entire pipeline |

### 2.2 Proposed Architecture — Solutions

| Problem → Solution | Mechanism |
|-------------------|-----------|
| Single camera → Multi-camera | One `CameraWorker` subprocess per camera |
| No reconnect → Auto-reconnect | `RTSPReader` background thread with exponential backoff |
| GIL bottleneck → Process isolation | `multiprocessing.Process` bypasses GIL |
| Frame buffer lag → Frame dropping | Queue size=2, discard stale frames, keep latest |
| No isolation → Crash containment | Worker crash detected by `CameraManager`, restarted automatically |

---

## 3. Component Design

### 3.1 RTSPReader

**Role:** Background thread that continuously reads frames from an RTSP stream.

| Attribute | Detail |
|-----------|--------|
| Runs as | Thread within CameraWorker process |
| Input | RTSP URL string |
| Output | Latest frame (non-blocking `get_nowait`) |
| Buffer | `queue.Queue(maxsize=2)` — oldest frame dropped when full |

**Responsibilities:**
- Open RTSP connection via `cv2.VideoCapture`
- Set `CAP_PROP_BUFFERSIZE = 1` to minimize OS-level buffering
- Run `cap.read()` in a tight loop on a background thread
- On read failure: close connection, wait with exponential backoff, reconnect
- Expose `is_alive()` and `get_frame()` to the parent worker

**Reconnect policy:**

```
Attempt 1: wait 1s
Attempt 2: wait 2s
Attempt 3: wait 4s
...
Attempt N: wait min(2^(N-1), 30)s  ← capped at 30s
```

---

### 3.2 CameraWorker (Process)

**Role:** Complete processing pipeline for one camera, isolated in a subprocess.

```
RTSPReader (thread)
      │  frame
      ▼
YOLO11 Detector  (GPU inference — shares device with other workers via CUDA)
      │  detections + frame
      ▼
BoTSORT Tracker  (CPU — per-process state, no sharing needed)
      │  tracked objects
      ▼
DetectionPublisher  (Pulsar + GCS)
```

**Isolation benefits:**
- Crash in Worker 1 does not affect Workers 2–4
- Separate Python interpreter → no GIL contention between workers
- Independent Pulsar producer, Redis client, GCS client per worker

**GPU sharing:**
- All workers use `device = "cuda:0"` (same physical GPU)
- CUDA driver handles concurrent kernel scheduling
- YOLO11 model weights loaded independently per process (shared page cache at OS level)

---

### 3.3 CameraManager (Orchestrator)

**Role:** Main process that supervises all camera workers.

| Method | Description |
|--------|-------------|
| `start_all()` | Load camera configs, spawn one `CameraWorker` per enabled camera |
| `stop_all()` | Send SIGTERM to all workers, wait for graceful shutdown (timeout 5s), then SIGKILL |
| `health_check()` | Called every 10s — check `process.is_alive()` for each worker |
| `restart_dead_workers()` | Respawn any worker that has exited unexpectedly |

**Signal handling:**
- `SIGTERM` / `SIGINT` → call `stop_all()`, then exit cleanly
- Ensures no orphan subprocesses remain after container stop

**Config source:** `cameras.yaml` on startup; optionally sync from PostgreSQL `core.cameras` table.

---

### 3.4 DetectionPublisher

**Role:** Emit detection results to Pulsar and upload sampled frames to GCS.

| Output | Content | Rate |
|--------|---------|------|
| Pulsar topic | Detection metadata (JSON) | Every frame (~25 FPS) |
| GCS bucket | Frame image (JPEG, 80% quality) | 1 frame per second |

**Pulsar message schema (per frame):**
```json
{
  "pipeline_run_id": "...",
  "camera_id": "cam_01",
  "store_id": "store_001",
  "frame_index": 1500,
  "capture_ts": "2026-03-29T08:00:00.123Z",
  "image_size": {"width": 1920, "height": 1080},
  "detections": [
    {
      "track_id": 42,
      "class": "person",
      "conf": 0.87,
      "bbox": {"x1": 100, "y1": 200, "x2": 300, "y2": 600},
      "centroid": {"x": 200, "y": 400}
    }
  ]
}
```

**GCS path pattern:**
```
gs://{bucket}/frames/{YYYY-MM-DD}/{camera_id}/{HH-MM-SS}_{frame_idx:06d}.jpg
```

**Async GCS uploads:** `ThreadPoolExecutor(max_workers=2)` per publisher — GCS upload does not block the inference loop.

---

## 4. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     CAMERA SOURCES                               │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐            │
│  │ cam_01  │  │ cam_02  │  │ cam_03  │  │ cam_04  │            │
│  │ RTSP    │  │ RTSP    │  │ RTSP    │  │ RTSP    │            │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘            │
└───────┼────────────┼────────────┼────────────┼──────────────────┘
        │            │            │            │
        ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────────────┐
│                   CAMERA MANAGER (Main Process)                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Process Pool                           │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────┐ │   │
│  │  │ Worker 1   │ │ Worker 2   │ │ Worker 3   │ │Worker 4│ │   │
│  │  │ (cam_01)   │ │ (cam_02)   │ │ (cam_03)   │ │(cam_04)│ │   │
│  │  │            │ │            │ │            │ │        │ │   │
│  │  │┌──────────┐│ │┌──────────┐│ │┌──────────┐│ │┌──────┐│ │   │
│  │  ││RTSPReader││ ││RTSPReader││ ││RTSPReader││ ││RTSP  ││ │   │
│  │  │└────┬─────┘│ │└────┬─────┘│ │└────┬─────┘│ │└──┬───┘│ │   │
│  │  │     ▼      │ │     ▼      │ │     ▼      │ │   ▼    │ │   │
│  │  │┌──────────┐│ │┌──────────┐│ │┌──────────┐│ │┌──────┐│ │   │
│  │  ││  YOLO11  ││ ││  YOLO11  ││ ││  YOLO11  ││ ││YOLO11││ │   │
│  │  ││ (GPU:0)  ││ ││ (GPU:0)  ││ ││ (GPU:0)  ││ ││GPU:0 ││ │   │
│  │  │└────┬─────┘│ │└────┬─────┘│ │└────┬─────┘│ │└──┬───┘│ │   │
│  │  │     ▼      │ │     ▼      │ │     ▼      │ │   ▼    │ │   │
│  │  │┌──────────┐│ │┌──────────┐│ │┌──────────┐│ │┌──────┐│ │   │
│  │  ││ BoTSORT  ││ ││ BoTSORT  ││ ││ BoTSORT  ││ ││BoT   ││ │   │
│  │  │└────┬─────┘│ │└────┬─────┘│ │└────┬─────┘│ │└──┬───┘│ │   │
│  │  │     ▼      │ │     ▼      │ │     ▼      │ │   ▼    │ │   │
│  │  │┌──────────┐│ │┌──────────┐│ │┌──────────┐│ │┌──────┐│ │   │
│  │  ││Publisher ││ ││Publisher ││ ││Publisher ││ ││Pub   ││ │   │
│  │  │└──────────┘│ │└──────────┘│ │└──────────┘│ │└──────┘│ │   │
│  │  └────────────┘ └────────────┘ └────────────┘ └────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                    Health Check Loop (10s)                       │
│                    Auto-restart dead workers                     │
└──────────────────────────────┼───────────────────────────────────┘
                               │
                               ▼
              ┌────────────────┴────────────────┐
              │                                 │
              ▼                                 ▼
┌─────────────────────────┐       ┌─────────────────────────┐
│      Apache Pulsar      │       │  Google Cloud Storage   │
│  detections (metadata)  │       │    frames (sampled)     │
│  - camera_id            │       │  gs://bucket/frames/    │
│  - track_id             │       │    YYYY-MM-DD/          │
│  - bbox, confidence     │       │      cam_01/            │
│  - timestamp            │       │        HH-MM-SS_xxx.jpg │
└─────────────────────────┘       └─────────────────────────┘
```

---

## 5. Bottleneck Analysis & Prevention

### 5.1 Potential Bottlenecks

| Bottleneck | Root Cause | Solution |
|------------|------------|----------|
| Python GIL | Only 1 thread executes Python bytecode at a time | Multi-process instead of multi-thread |
| RTSP Buffer Lag | OpenCV buffers 5–10 frames by default | Set `CAP_PROP_BUFFERSIZE=1`; queue with frame dropping |
| GPU Memory (OOM) | Multiple YOLO instances load weights separately | Use YOLO11n/s; FP16 inference; one model per process |
| GCS Upload Blocking | Synchronous HTTP upload blocks inference loop | `ThreadPoolExecutor` for async uploads |
| Pulsar Publish Blocking | Synchronous `send()` blocks per frame | Async producer with batching enabled |
| Camera Disconnect | Network instability, camera reboot | Auto-reconnect with exponential backoff in RTSPReader |

### 5.2 Performance Optimizations

- **Frame skipping**: If inference takes longer than `1/fps` seconds, drop the buffered frame and process the next one
- **FP16 inference**: `model.half()` halves VRAM usage with minimal accuracy loss on T4
- **Model size selection**: YOLO11n for 6–8 cameras; YOLO11s for 4 cameras with higher accuracy
- **Async everywhere**: Non-blocking I/O for Pulsar, GCS, Redis; no synchronous waits in the hot path

---

## 6. Resource Estimation

### 6.1 Per-Camera Resource Requirements

| Component | CPU | RAM | GPU VRAM | Network |
|-----------|-----|-----|----------|---------|
| RTSP Decode (ffmpeg) | 0.3 core | 200 MB | — | 2–5 Mbps |
| YOLO11n Inference | 0.5 core | 500 MB | 1 GB | — |
| YOLO11s Inference | 0.8 core | 800 MB | 2 GB | — |
| BoTSORT Tracking | 0.2 core | 300 MB | 0.5 GB | — |
| Heatmap Calculation | 0.1 core | 100 MB | — | — |
| Publisher (Pulsar + GCS) | 0.1 core | 100 MB | — | 0.5 Mbps |
| **Total (YOLO11n)** | **~1.2 cores** | **~1.2 GB** | **~1.5 GB** | **~3 Mbps** |
| **Total (YOLO11s)** | **~1.5 cores** | **~1.5 GB** | **~2.5 GB** | **~3 Mbps** |

### 6.2 Infrastructure Overhead

| Service | CPU | RAM | Notes |
|---------|-----|-----|-------|
| Pulsar Standalone | 1 core | 1 GB | Message broker |
| Flink (JM + TM) | 2 cores | 3 GB | Stream processing |
| PostgreSQL | 0.5 core | 512 MB | Metadata storage |
| Redis | 0.2 core | 256 MB | Real-time cache |
| Trino | 1 core | 2 GB | Query engine |
| Streamlit + FastAPI | 0.5 core | 512 MB | Dashboard + API |
| Grafana + Prometheus | 0.3 core | 512 MB | Monitoring |
| Docker overhead | 0.5 core | 1 GB | Container runtime |
| **Total Infrastructure** | **~6 cores** | **~9 GB** | |

### 6.3 GCP VM Recommendations

| Cameras | Machine Type | vCPU | RAM | GPU | Storage | Est. Monthly |
|---------|--------------|------|-----|-----|---------|--------------|
| 1–2 | n1-standard-4 | 4 | 15 GB | T4 (16 GB) | 100 GB SSD | ~$250 |
| 3–4 | n1-standard-8 | 8 | 30 GB | T4 (16 GB) | 200 GB SSD | ~$350 |
| 5–6 | n1-standard-8 | 8 | 30 GB | T4 (16 GB) | 200 GB SSD | ~$350 |
| 7–8 | n1-standard-16 | 16 | 60 GB | T4 (16 GB) | 500 GB SSD | ~$500 |
| 8+ | Multiple VMs or larger GPU | — | — | — | — | — |

**Recommended for thesis demo:** `n1-standard-8` + NVIDIA T4 — supports 4 cameras with headroom for all infrastructure services.

---

## 7. Deployment Architecture

### 7.1 Docker Compose Services

```yaml
services:
  # Vision Service
  vision:
    # Multi-process Python app (CameraManager + CameraWorker subprocesses)
    # GPU access via NVIDIA container runtime
    # runtime: nvidia
    # Mounts: /configs (cameras.yaml), /models (YOLO weights), /secrets (GCS key)
    # Depends on: pulsar, redis, postgres

  # Infrastructure
  pulsar:
    # Apache Pulsar standalone
    # Ports: 6650 (broker), 8084 (admin UI)
    # Volume: pulsar-data (message persistence)

  redis:
    # Redis 7 with AOF persistence
    # Port: 6379
    # Memory policy: allkeys-lru, limit 512MB
    # Volume: redis-data

  postgres:
    # PostgreSQL 16
    # Port: 5432
    # Volume: postgres-data
    # Init: /infra/postgres/init.sql (schema creation)

  flink-jobmanager:
    # Flink 1.18 JobManager
    # Port: 8081 (Web UI)
    # Volume: flink-checkpoints

  flink-taskmanager:
    # Flink 1.18 TaskManager
    # Task slots: 4 (configurable)
    # Memory: 2 GB task heap

  # Presentation
  api:
    # FastAPI + Uvicorn
    # Port: 8000
    # Workers: 2

  streamlit:
    # Streamlit dashboard
    # Port: 8501

  grafana:
    # Grafana 11.3
    # Port: 3000
    # Historical KPI analytics only (not real-time)
```

### 7.2 Network Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         rva-net                                  │
│                     (Docker bridge network)                      │
│                                                                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │ vision  │ │ pulsar  │ │  redis  │ │postgres │ │  flink  │   │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘   │
│                                                                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                           │
│  │   api   │ │streamlit│ │ grafana │                           │
│  │  :8000  │ │  :8501  │ │  :3000  │                           │
│  └────┬────┘ └────┬────┘ └────┬────┘                           │
└───────┼───────────┼───────────┼─────────────────────────────────┘
        │           │           │
        ▼           ▼           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Nginx / Traefik                               │
│                   (Reverse Proxy + SSL)                          │
│                                                                  │
│  api.rva.example.com       → :8000                              │
│  dashboard.rva.example.com → :8501                              │
│  monitor.rva.example.com   → :3000                              │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                        External Access
                          (HTTPS :443)
```

### 7.3 Volume Mounts

| Volume | Container Path | Purpose | Persistence |
|--------|----------------|---------|-------------|
| `postgres-data` | `/var/lib/postgresql/data` | Database files | Required |
| `redis-data` | `/data` | Redis AOF log | Required |
| `pulsar-data` | `/pulsar/data` | Message storage | Required |
| `flink-checkpoints` | `/checkpoints` | Flink state backend | Required |
| `grafana-data` | `/var/lib/grafana` | Dashboards + settings | Optional |
| `models` | `/app/data/models` | YOLO weights | Read-only |
| `configs` | `/app/configs` | `cameras.yaml` | Read-only |
| `secrets` | `/secrets` | GCS service account key | Read-only |

---

## 8. Configuration Management

### 8.1 Camera Configuration (`cameras.yaml`)

```yaml
cameras:
  - camera_id: cam_01
    name: "Entrance Camera"
    rtsp_url: "rtsp://admin:password@192.168.1.101:554/stream1"
    store_id: store_001
    location: "Main entrance"
    fps: 25
    resolution: "1920x1080"
    enabled: true

  - camera_id: cam_02
    name: "Checkout Area"
    rtsp_url: "rtsp://admin:password@192.168.1.102:554/stream1"
    store_id: store_001
    location: "Checkout counter"
    fps: 25
    resolution: "1920x1080"
    enabled: true

settings:
  reconnect_delay_initial: 1      # seconds (first retry wait)
  reconnect_delay_max: 30         # seconds (maximum backoff cap)
  health_check_interval: 10       # seconds (CameraManager loop)
  frame_queue_size: 2             # frames buffered in RTSPReader queue
  gcs_upload_interval: 1          # seconds (1 keyframe/second to GCS)
```

### 8.2 Environment Variables

```env
# Vision model
VISION_MODEL_PATH=/app/data/models/yolo11n.pt
VISION_DEVICE=cuda:0
VISION_CONFIDENCE_THRESHOLD=0.5
VISION_IOU_THRESHOLD=0.45

# Google Cloud Storage
GCS_PROJECT_ID=my-gcp-project
GCS_BUCKET_NAME=rva-frames
GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcs.json

# Apache Pulsar
PULSAR_SERVICE_URL=pulsar://pulsar:6650
PULSAR_TOPIC_DETECTIONS=persistent://rva/ingest/detections

# Redis
REDIS_URL=redis://redis:6379

# PostgreSQL
POSTGRES_DSN=postgresql://rva:password@postgres:5432/rva_metadata
```

---

## 9. Failure Handling & Recovery

### 9.1 Failure Scenarios

| Scenario | Detection | Recovery | RTO |
|----------|-----------|----------|-----|
| Camera disconnect | `RTSPReader` read timeout | Auto-reconnect (exponential backoff) | 1–30s |
| Worker process crash | `CameraManager` health check (10s loop) | Respawn subprocess | 10–15s |
| GPU OOM | `torch.cuda.OutOfMemoryError` | Reduce batch, restart worker | 15–30s |
| Pulsar unavailable | Connection exception on producer | Retry with backoff; buffer last N messages | Depends on Pulsar |
| GCS upload failure | HTTP 5xx / timeout | Retry 3× with 1s delay; skip frame after 3 failures | 5–10s |
| Redis unavailable | `ConnectionError` | Log warning; continue pipeline without cache | 0s (non-blocking) |
| All workers dead | All `process.is_alive()` return False | `restart_dead_workers()` respawns all | 10–15s |

### 9.2 Graceful Shutdown

On `SIGTERM` or `SIGINT`:

```
1. CameraManager catches signal
2. Calls stop_all():
   a. Send SIGTERM to all CameraWorker processes
   b. Wait up to 5 seconds for each to exit
   c. SIGKILL any that remain after timeout
3. CameraManager exits with code 0
```

### 9.3 Monitoring & Alerting

| Metric | Source | Alert Threshold |
|--------|--------|-----------------|
| Camera online status | CameraManager logs | Any camera offline > 1 minute |
| Processing FPS | Worker metrics | FPS < 50% of target FPS |
| GPU utilization | `nvidia-smi` / Prometheus | > 95% sustained for 5 min |
| GPU memory | `nvidia-smi` / Prometheus | > 90% of VRAM used |
| Pulsar consumer lag | Pulsar metrics endpoint | > 1,000 unprocessed messages |
| Worker restart count | CameraManager metrics | > 3 restarts/hour for same camera |

---

## 10. Scalability Considerations

### 10.1 Vertical Scaling (Single VM)

- Add CPU cores: linear benefit for tracking and publishing
- Upgrade GPU: T4 (16 GB) → A10 (24 GB) → A100 (40 GB)
- Practical ceiling: **8–12 cameras per T4** depending on model size
- Beyond 12 cameras on T4: GPU VRAM becomes the bottleneck

### 10.2 Horizontal Scaling (Multiple VMs)

When to consider: > 8 cameras, or cameras distributed across multiple store locations.

```
Store A (VM 1)          Store B (VM 2)
┌─────────────────┐    ┌─────────────────┐
│ CameraManager   │    │ CameraManager   │
│ cam_01..cam_04  │    │ cam_05..cam_08  │
└────────┬────────┘    └────────┬────────┘
         │                      │
         └──────────┬───────────┘
                    │
                    ▼
          ┌─────────────────┐
          │  Pulsar Cluster │  (centralized)
          └────────┬────────┘
                   │
                   ▼
          ┌─────────────────┐
          │  Flink + Iceberg│  (centralized)
          │  GCS (shared)   │
          └─────────────────┘
```

Considerations:
- Partition Pulsar topics by `camera_id` or `store_id` for consumer isolation
- Flink jobs key by `camera_id` — no change needed for horizontal scale
- GCS bucket is shared; path prefix by `store_id` keeps data organized

### 10.3 Future Improvements

| Improvement | When | Benefit |
|-------------|------|---------|
| Batch inference | > 4 cameras, same GPU | Higher throughput, better GPU utilization |
| TensorRT / ONNX export | Production hardening | 2–4× faster inference on NVIDIA hardware |
| Triton Inference Server | Model serving at scale | Centralized model management, HTTP/gRPC API |
| Edge deployment (Jetson) | Low-bandwidth stores | Process video at edge, send metadata only |
| Kubernetes | > 3 VMs | Automated scaling, rolling updates |

---

## 11. Testing Strategy

### 11.1 Unit Tests

| Component | Test Approach |
|-----------|--------------|
| `RTSPReader` | Mock `cv2.VideoCapture`; simulate read failure → verify reconnect attempts |
| `CameraManager` | Mock `multiprocessing.Process`; simulate process death → verify restart |
| `DetectionPublisher` | Mock Pulsar producer and GCS client; verify message schema and upload rate |

### 11.2 Integration Tests

| Scenario | Setup |
|----------|-------|
| Full pipeline with video file | Replace RTSP URL with local `.mp4`; verify detections reach Pulsar |
| Pulsar → Flink → PostgreSQL | Run full Flink jobs; verify `track_events` rows inserted |
| GCS upload | Upload test frame; verify `gs://` path returned matches pattern |

### 11.3 Load Tests

| Test | Method | Target |
|------|--------|--------|
| N-camera simulation | Run N workers with video files in loop | 4 cameras at 25 FPS each |
| Sustained throughput | Run for 30 minutes | < 5% frame drops |
| Memory leak check | Monitor RSS over time | RSS stable after 10 minutes |
| GPU VRAM | `nvidia-smi` during load | < 80% at 4 cameras (YOLO11n) |

### 11.4 Chaos Tests

| Chaos Scenario | Verification |
|----------------|-------------|
| Kill random `CameraWorker` process | CameraManager restarts it within 15s |
| Block RTSP port for 60s | RTSPReader retries; reconnects when port reopens |
| Fill `/tmp` disk | Publisher skips GCS upload gracefully; logs error |
| `redis-cli SHUTDOWN` | Vision pipeline continues; logs warning |
| Pulsar container stop | Publisher buffers and retries; resumes when Pulsar restarts |

---

## 12. Implementation Roadmap

| Phase | Tasks | Duration |
|-------|-------|----------|
| **Phase 1** | `RTSPReader` — background thread, queue, reconnect logic | 2 days |
| **Phase 2** | `CameraWorker` — single process wrapping existing YOLO + BoTSORT | 2 days |
| **Phase 3** | `CameraManager` — subprocess pool, health check, auto-restart | 2 days |
| **Phase 4** | `DetectionPublisher` — Pulsar async producer, GCS async upload | 2 days |
| **Phase 5** | Docker Compose integration — GPU runtime, cameras.yaml mount | 1 day |
| **Phase 6** | Monitoring — Prometheus metrics, Grafana alerts | 1 day |
| **Phase 7** | Testing & optimization — load tests, chaos tests, tuning | 2 days |
| **Total** | | **12 days** |

---

## Related Documents

- [01_ARCHITECTURE_ANALYSIS.md](./01_ARCHITECTURE_ANALYSIS.md) — System architecture overview
- [02_ARCHITECTURE_IMPROVED.md](./02_ARCHITECTURE_IMPROVED.md) — Dual-Path architecture
- [07_VISION_MODULE_CHANGES.md](./07_VISION_MODULE_CHANGES.md) — FrameSaver & TrackLifecycleManager
- [08_PROJECT_STRUCTURE.md](./08_PROJECT_STRUCTURE.md) — Monorepo layout
