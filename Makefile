# ── Setup ────────────────────────────────────────────────
install:       ## Install all workspace dependencies
	uv sync

setup-gcp:     ## Create GCS bucket and set lifecycle policy
	bash scripts/setup_gcp.sh

# ── Run (local) ──────────────────────────────────────────
run-vision:    ## Run vision service (multi-camera, reads cameras.yaml)
	uv run rva-vision

run-vision-dev: ## Run vision with alternate dev camera config
	CAMERAS_CONFIG_PATH=configs/cameras.dev.yaml uv run rva-vision

run-vision-test: ## Run vision with a local video file instead of RTSP
	VIDEO_PATH=data/videos/test.mp4 uv run rva-vision

run-api:       ## Run API service locally
	uv run rva-api

run-streamlit: ## Run Streamlit dashboard locally
	uv run rva-dashboard

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

.PHONY: install setup-gcp run-vision run-api run-streamlit \
        up up-infra down logs build \
        build-flink submit-flink-fast submit-flink-slow \
        migrate test test-unit test-integration lint format typecheck
