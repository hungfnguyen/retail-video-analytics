# Project Structure

## Table of Contents

1. [Overview](#1-overview)
2. [Directory Layout](#2-directory-layout)
3. [Python Workspace (uv)](#3-python-workspace-uv)
4. [Shared Packages](#4-shared-packages)
5. [Docker Compose](#5-docker-compose)
6. [Makefile Commands](#6-makefile-commands)
7. [Migration Map](#7-migration-map)
8. [Environment Variables](#8-environment-variables)

---

## 1. Overview

RVA is a **Python monorepo** managed by [uv workspaces](https://docs.astral.sh/uv/concepts/workspaces/). Code is organized into three layers:

| Layer | Path | Purpose |
|-------|------|---------|
| Shared libraries | `packages/` | Models, storage clients, messaging — imported by all services |
| Deployable services | `services/` | Vision, Flink, API, Streamlit — each runs as its own container |
| Infrastructure config | `infra/` | Flink, Pulsar, Iceberg, Grafana, PostgreSQL config files |

Flink jobs are written in **Scala** and built with `sbt`. All other services are Python 3.11.

---

## 2. Directory Layout

```
retail-video-analytics/
│
├── pyproject.toml              # uv workspace root
├── uv.lock                     # unified lock file (auto-generated)
├── .python-version             # 3.11
├── .env.example
├── .gitignore
├── README.md
├── Makefile
│
├── docker/
│   ├── docker-compose.yml      # base: infra + app services
│   ├── docker-compose.dev.yml  # dev overrides (volume mounts, hot reload)
│   ├── docker-compose.prod.yml # prod overrides (resource limits, restart)
│   ├── vision/Dockerfile       # nvidia runtime, YOLO deps
│   ├── flink/Dockerfile        # Scala + sbt build
│   ├── api/Dockerfile
│   └── streamlit/Dockerfile
│
├── packages/
│   ├── rva-core/               # Pydantic models + settings
│   ├── rva-storage/            # GCS, PostgreSQL, Redis clients
│   └── rva-messaging/          # Pulsar producer/consumer
│
├── services/
│   ├── vision/                 # YOLO11 + BoTSORT + frame publisher
│   ├── flink-jobs/             # Scala — fast path CEP + slow path Medallion
│   ├── api/                    # FastAPI — REST + WebSocket
│   └── streamlit/              # Streamlit dashboard
│
├── infra/
│   ├── flink/                  # flink-conf.yaml
│   ├── pulsar/                 # standalone.conf
│   ├── iceberg/                # catalog.yaml
│   ├── grafana/                # dashboards + provisioning
│   └── postgres/               # init.sql (schema)
│
├── scripts/
│   ├── setup_gcp.sh            # create GCS bucket + lifecycle policy
│   ├── download_models.py      # download YOLO weights
│   ├── generate_test_data.py
│   └── migrate_db.py
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── docs/                       # project documentation
├── data/                       # gitignored — videos, models, output
└── notebooks/
```

---

## 3. Python Workspace (uv)

### Root `pyproject.toml`

```toml
[tool.uv.workspace]
members = [
    "packages/rva-core",
    "packages/rva-storage",
    "packages/rva-messaging",
    "services/vision",
    "services/api",
    "services/streamlit",
]

[tool.uv]
python = "3.11"
```

### Service `pyproject.toml` (example: vision)

```toml
[project]
name = "rva-vision"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "rva-core",
    "rva-storage",
    "rva-messaging",
    "ultralytics>=8.2",
    "opencv-python-headless>=4.9",
]

[project.scripts]
rva-vision = "vision.main:main"   # entry point: uv run rva-vision

[tool.uv.sources]
rva-core      = { workspace = true }
rva-storage   = { workspace = true }
rva-messaging = { workspace = true }
```

Entry points follow the same pattern for every service:

| Service | Entry point |
|---------|-------------|
| `rva-vision` | `vision.main:main` |
| `rva-api` | `api.main:main` |
| `rva-streamlit` | `streamlit_app.app:main` |

---

## 4. Shared Packages

### `rva-core` — Models & Config

Pydantic data models (`Detection`, `Track`, `Alert`, `HeatmapCell`) and a shared `Settings` class loaded from `.env`. No external I/O — pure Python.

### `rva-storage` — Storage Clients

| Module | Client | Used by |
|--------|--------|---------|
| `gcs.py` | `GCSClient` — upload/download frames, signed URLs | vision, api |
| `postgres.py` | `PostgresClient` — asyncpg pool, track events | vision, api |
| `redis_client.py` | `RedisClient` — heatmap grid, pub/sub, alert queue | vision, api, streamlit |

### `rva-messaging` — Pulsar Client

`DetectionProducer` (used by vision) and `DetectionConsumer` (used by flink-jobs Python wrapper). Message schemas defined as dataclasses in `schemas.py`.

---

## 5. Docker Compose

All services — infrastructure and application — are defined in `docker/docker-compose.yml`.

### Infrastructure services

```yaml
services:
  pulsar:
    image: apachepulsar/pulsar:3.3.2

  flink-jobmanager:
    image: flink:1.18

  flink-taskmanager:
    image: flink:1.18

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: rva_metadata
      POSTGRES_USER: rva
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - ./infra/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql

  trino:
    image: trinodb/trino:418

  grafana:
    image: grafana/grafana:11.3.0
```

### Application services

```yaml
  vision:
    build:
      context: ..
      dockerfile: docker/vision/Dockerfile
    runtime: nvidia                      # GPU support
    environment:
      - GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcs-key.json
      - PULSAR_SERVICE_URL=pulsar://pulsar:6650
      - POSTGRES_DSN=postgresql://rva:${POSTGRES_PASSWORD}@postgres:5432/rva_metadata
      - REDIS_URL=redis://redis:6379
    volumes:
      - ./data/videos:/app/data/videos
      - ${GCS_KEY_PATH}:/secrets/gcs-key.json:ro
    depends_on:
      redis: { condition: service_healthy }
      postgres: { condition: service_healthy }

  api:
    build:
      context: ..
      dockerfile: docker/api/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379
      - POSTGRES_DSN=postgresql://rva:${POSTGRES_PASSWORD}@postgres:5432/rva_metadata
      - GCS_FRAMES_BUCKET=${GCS_FRAMES_BUCKET}
    depends_on:
      redis: { condition: service_healthy }
      postgres: { condition: service_healthy }

  streamlit:
    build:
      context: ..
      dockerfile: docker/streamlit/Dockerfile
    ports:
      - "8501:8501"
    environment:
      - BACKEND_URL=http://api:8000
      - GCS_FRAMES_BUCKET=${GCS_FRAMES_BUCKET}
    depends_on:
      - api
```

### Dev overrides (`docker-compose.dev.yml`)

```yaml
services:
  vision:
    volumes:
      - ../services/vision:/app/services/vision  # hot reload
    command: uv run --reload rva-vision

  api:
    volumes:
      - ../services/api:/app/services/api
    command: uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 6. Makefile Commands

```makefile
# ── Setup ────────────────────────────────────────────────
install:       ## Install all workspace dependencies
	uv sync

setup-gcp:     ## Create GCS bucket and set lifecycle policy
	bash scripts/setup_gcp.sh

# ── Run (local) ──────────────────────────────────────────
run-vision:    ## Run vision service locally
	uv run rva-vision

run-api:       ## Run API service locally
	uv run rva-api

run-streamlit: ## Run Streamlit dashboard locally
	uv run rva-streamlit

# ── Docker ───────────────────────────────────────────────
up:            ## Start all services (dev)
	docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d

up-infra:      ## Start infrastructure only (no app services)
	docker compose -f docker/docker-compose.yml up -d \
	  pulsar flink-jobmanager flink-taskmanager redis postgres trino grafana

down:          ## Stop all services
	docker compose -f docker/docker-compose.yml down

logs:          ## Follow logs for all services
	docker compose -f docker/docker-compose.yml logs -f

build:         ## Build all Docker images
	docker compose -f docker/docker-compose.yml build

# ── Flink ────────────────────────────────────────────────
build-flink:   ## Compile Flink Scala JAR (sbt assembly)
	cd services/flink-jobs && sbt assembly

submit-flink-fast: ## Submit fast path CEP job to Flink cluster
	docker exec flink-jobmanager flink run \
	  /opt/flink/jobs/flink-jobs-assembly.jar \
	  --class org.rva.FastPathJob

submit-flink-slow: ## Submit slow path Medallion job to Flink cluster
	docker exec flink-jobmanager flink run \
	  /opt/flink/jobs/flink-jobs-assembly.jar \
	  --class org.rva.SlowPathJob

# ── Database ─────────────────────────────────────────────
migrate:       ## Run database migrations
	uv run python scripts/migrate_db.py

# ── Quality ──────────────────────────────────────────────
test:          ## Run all tests
	uv run pytest tests/

test-unit:     ## Run unit tests only
	uv run pytest tests/unit/

test-integration: ## Run integration tests
	uv run pytest tests/integration/

lint:          ## Lint all Python code
	uv run ruff check .

format:        ## Format all Python code
	uv run ruff format .

typecheck:     ## Type-check all Python code
	uv run mypy packages/ services/
```

---

## 7. Migration Map

| Current path | New path | Change |
|---|---|---|
| `vision/` | `services/vision/` | Restructured as uv package |
| `ai/` | _(deleted)_ | Duplicate of `vision/` |
| `flink-jobs/java/` | `services/flink-jobs/` | Rewritten in Scala (sbt) |
| `infrastructure/flink/` | `infra/flink/` | Renamed |
| `infrastructure/pulsar/` | `infra/pulsar/` | Renamed |
| `infrastructure/grafana/` | `infra/grafana/` | Renamed |
| `infrastructure/trino/` | `infra/trino/` | Renamed |
| `infrastructure/minio/` | _(deleted)_ | Replaced by GCS |
| `infrastructure/airflow/` | _(deleted)_ | Not used |
| `docker-compose.yml` (root) | `docker/docker-compose.yml` | Moved; includes app services |
| `assets/docs/` | `docs/` | Promoted to root |
| `setup.txt` | `pyproject.toml` per package | Replaced by uv |
| _(none)_ | `packages/rva-core/` | New |
| _(none)_ | `packages/rva-storage/` | New |
| _(none)_ | `packages/rva-messaging/` | New |
| _(none)_ | `services/api/` | New |
| _(none)_ | `services/streamlit/` | New |

---

## 8. Environment Variables

Copy `.env.example` → `.env`:

```env
# ── Camera / Store ───────────────────────────────────────
CAMERA_ID=cam_01
STORE_ID=store_01

# ── Google Cloud Storage ─────────────────────────────────
GCS_PROJECT_ID=my-gcp-project
GCS_FRAMES_BUCKET=rva-frames
GCS_KEY_PATH=/path/to/service-account.json
GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcs-key.json

# ── Pulsar ───────────────────────────────────────────────
PULSAR_SERVICE_URL=pulsar://pulsar:6650
PULSAR_TOPIC=persistent://retail/metadata/events

# ── PostgreSQL ───────────────────────────────────────────
POSTGRES_DSN=postgresql://rva:rva_secret@postgres:5432/rva_metadata
POSTGRES_PASSWORD=rva_secret

# ── Redis ────────────────────────────────────────────────
REDIS_URL=redis://redis:6379

# ── Vision ───────────────────────────────────────────────
MODEL_NAME=yolo11l.pt
VIDEO_PATH=data/videos/sample.mp4
TRACKER_TYPE=botsort
CONF_THRES=0.25
FRAME_SAVE_INTERVAL=1

# ── Alerting ─────────────────────────────────────────────
CROWD_THRESHOLD=20
DENSITY_THRESHOLD=30
HEATMAP_DECAY_INTERVAL=3
```

---

## Related Documents

- [01_ARCHITECTURE_ANALYSIS.md](./01_ARCHITECTURE_ANALYSIS.md) - System architecture
- [02_ARCHITECTURE_IMPROVED.md](./02_ARCHITECTURE_IMPROVED.md) - Dual-Path design
- [05_ACTION_PLAN.md](./05_ACTION_PLAN.md) - Implementation guide
- [06_TECH_COMPARISON.md](./06_TECH_COMPARISON.md) - Technology decisions
- [07_VISION_MODULE_CHANGES.md](./07_VISION_MODULE_CHANGES.md) - Vision module components
