# Project Structure Index - Retail Video Analytics
> Auto-generated (respects .gitignore). Last updated: 2026-01-02 10:46

## Quick Stats
- **Total files**: 72 (project files only, excludes .gitignore patterns)
- **Project type**: Data Engineering / Stream Processing
- **Main language**: Python (Vision AI), Java (Flink Jobs)
- **Stack**: YOLO11 + BoTSORT → Apache Pulsar → Apache Flink → Apache Iceberg (MinIO) → Trino → Grafana

## Core Project Structure

```
retail-video-analytics/
├── vision/                          # Vision AI Module (Python)
│   ├── main.py                      # Entry point - chạy detection/tracking pipeline
│   ├── config/settings.py           # Config centralized
│   ├── detect/
│   │   ├── yolo_detector.py        # YOLO11 detector wrapper
│   │   ├── models/                 # YOLO model weights (.pt files)
│   │   └── coco_classes.txt        # Class labels
│   ├── track/
│   │   ├── tracker_factory.py      # Factory tạo tracker instances
│   │   ├── yolo_tracker_botsort.py # BoTSORT tracker (hiện dùng)
│   │   ├── yolo_tracker_bytetrack.py # ByteTrack tracker (alternative)
│   │   ├── deepsort_tracker.py     # DeepSORT tracker (deprecated)
│   │   └── config/                 # Tracker configs (botsort.yaml, bytetrack.yaml)
│   ├── ingest/
│   │   └── CVSource.py             # Video source reader (file/stream/camera)
│   ├── emit/
│   │   ├── pulsar_emitter.py       # Emit to Pulsar (production)
│   │   └── json_emitter.py         # Emit to local JSON file (debug)
│   ├── utils/
│   │   ├── visualizer.py           # Vẽ bbox lên frame
│   │   └── path_utils.py           # Path handling utilities
│   └── video/                      # Test video files
│
├── flink-jobs/                      # Flink Streaming Jobs (Java + SQL)
│   ├── java/
│   │   ├── pom.xml                 # Maven config
│   │   └── src/main/java/org/rva/
│   │       ├── BronzeIngestJob.java      # Bronze layer (raw ingest)
│   │       ├── silver/
│   │       │   └── SilverJob.java        # Silver layer (cleaning/enrichment)
│   │       └── gold/
│   │           ├── GoldMinuteByCamJob.java     # Gold aggregations
│   │           ├── GoldHourByCamJob.java
│   │           ├── GoldPeoplePerMinuteJob.java
│   │           ├── GoldZoneHeatmapJob.java
│   │           ├── GoldZoneDwellJob.java
│   │           └── GoldTrackSummaryJob.java
│   ├── lib/                        # Flink connector JARs
│   │   ├── flink-connector-pulsar-4.1.0-1.18.jar
│   │   └── pulsar-client-api-3.0.0.jar
│   └── sql/                        # SQL job definitions (alternative to Java)
│
├── infrastructure/                  # Docker infrastructure configs
│   ├── flink/
│   │   ├── Dockerfile
│   │   ├── conf/flink-conf.yaml    # Flink config (checkpointing, parallelism)
│   │   └── scripts/submit-jobs.sh  # Auto-submit 8 Flink jobs khi khởi động
│   ├── pulsar/
│   │   ├── conf/standalone.conf    # Pulsar broker config
│   │   ├── schema/metadata-json-schema.json
│   │   └── scripts/init-topics.sh  # Tạo topic retail/metadata/events
│   ├── minio/
│   │   ├── Dockerfile
│   │   └── scripts/init.sh         # Tạo bucket warehouse
│   ├── trino/
│   │   └── etc/
│   │       ├── config.properties
│   │       └── catalog/lakehouse.properties  # Iceberg catalog config
│   ├── grafana/
│   │   └── provisioning/
│   │       ├── datasources/trino.yaml
│   │       └── dashboards/
│   │           └── rva_traffic_overview.json  # Main dashboard
│   └── airflow/                    # (Future use - chưa active)
│       ├── Dockerfile
│       └── requirements.txt
│
├── notebooks/                       # Jupyter notebooks cho EDA & validation
│   ├── data_exploration.ipynb      # Bronze data exploration
│   ├── silver_explore.ipynb        # Silver layer validation
│   ├── gold_explore.ipynb          # Gold aggregations testing
│   └── explore_analytics.ipynb     # Full analytics pipeline testing
│
├── scripts/
│   └── replay_jsonl_to_pulsar.py   # Replay data từ JSONL vào Pulsar (testing)
│
├── docs/
│   ├── guide.md                    # End-to-end setup guide (QUAN TRỌNG)
│   ├── data-flow.md                # Data flow architecture
│   ├── architecture.png            # Architecture diagram
│   └── structure.md                # (File này)
│
├── configs/
│   └── .env.example                # Environment variables template
│
├── docker-compose.yml              # Orchestrate toàn bộ stack (8 services)
├── setup.txt                       # Python dependencies
├── README.md                       # Project overview
├── HANDOFF.md                      # Current status & next steps
├── CHANGELOG.md                    # Lịch sử thay đổi
└── AGENTS.md                       # AI Agent conventions
```

## Key Entry Points

| File | Purpose | When to Use |
|:---|:---|:---|
| [vision/main.py](vision/main.py) | Start Vision AI pipeline | Chạy detection/tracking và emit metadata |
| [docker-compose.yml](docker-compose.yml) | Infrastructure setup | `docker compose up -d` để start toàn bộ stack |
| [docs/guide.md](docs/guide.md) | Complete setup guide | Hướng dẫn chi tiết từ setup → run → verify |
| [infrastructure/flink/scripts/submit-jobs.sh](infrastructure/flink/scripts/submit-jobs.sh) | Flink job submission | Tự động chạy khi docker compose up |

## Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          VISION AI LAYER                            │
│  Video → YOLO11 Detection → BoTSORT Tracking → JSON Metadata       │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      MESSAGE TRANSPORT                              │
│  Apache Pulsar (persistent://retail/metadata/events)               │
│  Key_Shared subscription by camera_id                              │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    STREAM PROCESSING (Flink)                        │
│  Bronze → Silver → Gold (6 aggregations)                           │
│  Checkpointing: 60s, State backend: RocksDB                        │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    LAKEHOUSE (Iceberg on MinIO)                     │
│  Tables: bronze_raw, silver_detections, gold_*                     │
│  Format: Parquet, Partitioned by store_id                          │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│              ANALYTICS (Trino + Grafana)                            │
│  SQL queries → Real-time dashboards                                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Feature Domains

### 1. Vision AI (Python)
**Location**: `vision/`
**Purpose**: Object detection, tracking, metadata generation
**Key Files**:
- [vision/main.py](vision/main.py) - Pipeline orchestration
- [vision/detect/yolo_detector.py](vision/detect/yolo_detector.py) - YOLO11 wrapper
- [vision/track/yolo_tracker_botsort.py](vision/track/yolo_tracker_botsort.py) - BoTSORT tracking
- [vision/emit/pulsar_emitter.py](vision/emit/pulsar_emitter.py) - Pulsar integration

### 2. Stream Processing (Java/Flink)
**Location**: `flink-jobs/java/src/main/java/org/rva/`
**Purpose**: Bronze → Silver → Gold data transformations
**Key Files**:
- [BronzeIngestJob.java](flink-jobs/java/src/main/java/org/rva/BronzeIngestJob.java) - Raw ingest từ Pulsar
- [silver/SilverJob.java](flink-jobs/java/src/main/java/org/rva/silver/SilverJob.java) - Data cleaning & enrichment
- [gold/Gold*Job.java](flink-jobs/java/src/main/java/org/rva/gold/) - 6 aggregation jobs

### 3. Infrastructure (Docker)
**Location**: `infrastructure/`
**Purpose**: Service configs, init scripts, provisioning
**Key Files**:
- [flink/conf/flink-conf.yaml](infrastructure/flink/conf/flink-conf.yaml) - Flink settings
- [pulsar/scripts/init-topics.sh](infrastructure/pulsar/scripts/init-topics.sh) - Topic setup
- [grafana/provisioning/](infrastructure/grafana/provisioning/) - Dashboards & datasources

### 4. Analytics & Validation (Jupyter)
**Location**: `notebooks/`
**Purpose**: Data exploration, validation, ad-hoc analysis
**Key Files**:
- [explore_analytics.ipynb](notebooks/explore_analytics.ipynb) - Full pipeline testing
- [silver_explore.ipynb](notebooks/silver_explore.ipynb) - Silver validation
- [gold_explore.ipynb](notebooks/gold_explore.ipynb) - Gold metrics validation

## Configuration Files

| File | Purpose |
|:---|:---|
| [.env](configs/.env.example) | Credentials, URLs, feature flags |
| [vision/.env](vision/.env) | Vision module specific config (MODEL_NAME, TRACKER_TYPE) |
| [docker-compose.yml](docker-compose.yml) | Service definitions, ports, volumes, dependencies |
| [infrastructure/flink/conf/flink-conf.yaml](infrastructure/flink/conf/flink-conf.yaml) | Flink cluster config |
| [infrastructure/pulsar/conf/standalone.conf](infrastructure/pulsar/conf/standalone.conf) | Pulsar broker settings |
| [setup.txt](setup.txt) | Python dependencies |
| [flink-jobs/java/pom.xml](flink-jobs/java/pom.xml) | Maven dependencies |

## Database Schema (Iceberg Tables)

### Bronze Layer
- **bronze_raw**: Raw JSON from Pulsar
  - Columns: `ingest_ts`, `publish_ts`, `raw_payload` (JSON), `source_properties` (MAP)
  - Partition: `store_id`

### Silver Layer
- **silver_detections**: Cleaned & structured detections
  - Columns: `ts`, `camera_id`, `track_id`, `det_id`, `class_name`, `confidence`, `bbox`, `centroid`, `zone_id`
  - Rules: Null removal, deduplication, confidence >= 0.4

### Gold Layer (6 tables)
- **gold_minute_by_camera**: People count per minute per camera
- **gold_hour_by_camera**: People count per hour per camera
- **gold_people_per_minute**: System-wide people count per minute
- **gold_zone_heatmap**: Zone visit counts
- **gold_zone_dwell**: Zone dwell time statistics
- **gold_track_summary**: Track-level aggregations (duration, avg confidence)

## File Patterns (Glob Search)

| Looking for | Path Pattern |
|:---|:---|
| Python modules | `vision/**/*.py` |
| Java jobs | `flink-jobs/java/src/main/java/**/*.java` |
| Flink configs | `infrastructure/flink/conf/*.yaml` |
| Dashboards | `infrastructure/grafana/provisioning/dashboards/*.json` |
| Notebooks | `notebooks/*.ipynb` |
| Docker configs | `infrastructure/**/Dockerfile` |
| Init scripts | `infrastructure/**/scripts/*.sh` |
| Model weights | `vision/detect/models/**/*.pt` |

## Development Workflow

### 1. First Time Setup
```bash
# 1. Start infrastructure
docker compose up -d --build

# 2. Setup Python environment
python -m venv venv
source venv/Scripts/activate  # Windows
pip install -r setup.txt

# 3. Verify services
docker ps  # Check all 8 services running
```

### 2. Run Vision Pipeline
```bash
cd vision
python main.py
# → Generates metadata → Pulsar → Flink → Iceberg
```

### 3. Validate Data Flow
- **Pulsar UI**: http://localhost:8082 (check topic messages)
- **Flink UI**: http://localhost:8081 (check 8 running jobs)
- **MinIO**: http://localhost:9001 (check warehouse bucket)
- **Grafana**: http://localhost:3000 (check dashboards - admin/admin)
- **Trino**: http://localhost:8083 (query Iceberg tables)

### 4. Debug & Development
- **Notebooks**: Mở `notebooks/explore_analytics.ipynb` để test SQL queries
- **Logs**: `docker logs <service-name>` để xem logs
- **Replay data**: `python scripts/replay_jsonl_to_pulsar.py` để replay test data

## Important Notes

### Model Weights (.pt files)
- **Ignored by Git**: Chỉ track `yolov8n.pt` (base model)
- **Location**: `vision/detect/models/` và root folder
- **Current models**: yolo11x.pt (detection), osnet*.pt (ReID for tracking)

### File Cleanup Candidates
- `note.txt` - Temporary CLI commands (nên xóa hoặc move vào docs/)
- `*.pt` files ở root - Model weights không cần thiết (giữ trong vision/detect/models/)
- `.codex/` - Duplicate của `.claude/` (có thể xóa nếu không dùng)
- `data_exploration.html` - Generated notebook output (có thể gitignore)

### Missing/Recommended Files
- `.env` file - Cần tạo từ `.env.example`
- `tests/` directory - Unit tests cho Python & Java code
- `docs/api.md` - API documentation cho các service
- `CONTRIBUTING.md` - Contributing guidelines
- `LICENSE` - License file

## Recent Changes (from CHANGELOG.md)
- **2025-12-07**: Added traffic patterns dashboard
- **2025-12-06**: Dashboard logic review & performance recommendations
- **2025-12-05**: Fixed Iceberg REST dependency chain, Grafana time axis
- **2025-12-01**: README rewrite, auto Flink job submission
- **2025-11-25**: Redesigned 3 Grafana dashboards
- **2025-11-24**: Aligned Gold jobs with notebooks, added core dashboards
- **2025-11-20**: Fixed Flink SQL Bronze submit error

## Tech Stack Summary

| Layer | Technology | Version | Port |
|:---|:---|:---:|:---:|
| Vision AI | YOLO11, BoTSORT, OpenCV | Latest | - |
| Message Broker | Apache Pulsar | 3.3.2 | 8082 |
| Stream Processing | Apache Flink | 1.18 | 8081 |
| Storage | MinIO (S3) | Latest | 9000/9001 |
| Table Format | Apache Iceberg | 1.4+ | - |
| Catalog | Iceberg REST | 0.7.0 | 8181 |
| Query Engine | Trino | 418 | 8083 |
| Visualization | Grafana | 11.3 | 3000 |

---

## Update Instructions

Để cập nhật file này:
```bash
# Respect .gitignore (recommended)
python .claude/skills/project-index/scripts/scan_structure.py . 4 > docs/structure.md

# Ignore .gitignore if needed
python .claude/skills/project-index/scripts/scan_structure.py . 4 --no-gitignore > docs/structure_full.md
```

**Notes**:
- Script giờ tự động đọc và respect `.gitignore` patterns
- Bỏ qua: `.claude/`, `.codex/`, `venv/`, `target/`, `data/`, `*.pt` (model weights), v.v.
- Last scan: 2026-01-02 10:46 (72 files, 40 directories)
- Contact: [Add maintainer info]
