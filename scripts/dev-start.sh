#!/usr/bin/env bash
# dev-start.sh — Start the full RVA dev stack in a named tmux session.
#
# Usage:
#   ./scripts/dev-start.sh          # start everything (idempotent)
#   ./scripts/dev-start.sh stop     # kill the tmux session + docker stack
#
# Attach anytime:     tmux attach -t rva
# Switch windows:     Ctrl+b then 0 / 1 / 2 / 3
# Detach (keep running): Ctrl+b then d
set -uo pipefail   # NOT -e: we handle errors manually for clarity

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="rva"

# ── helpers ───────────────────────────────────────────────────────────────────

# Check if a container is running by listing all running container names
_container_running() {
    docker ps --format "{{.Names}}" 2>/dev/null | grep -qFx "$1"
}

_stack_healthy() {
    local required=("flink-jobmanager" "flink-taskmanager" "pulsar-broker" "redis" "iceberg-rest")
    for svc in "${required[@]}"; do
        if ! _container_running "$svc"; then
            echo "[rva] Container not running: $svc"
            return 1
        fi
    done
    return 0
}

_flink_running_jobs() {
    local count
    count=$(curl -sf http://localhost:8081/jobs 2>/dev/null \
        | python3 -c "
import json,sys
try: print(sum(1 for j in json.load(sys.stdin)['jobs'] if j['status']=='RUNNING'))
except: print(0)
" 2>/dev/null) || count=0
    echo "${count:-0}"
}

_wait_pulsar() {
    echo "[rva] Waiting for Pulsar broker (up to 120s)..."
    local attempt=0
    while [ $attempt -lt 40 ]; do
        if docker exec pulsar-broker bin/pulsar-admin brokers healthcheck \
               --url http://localhost:8080 >/dev/null 2>&1; then
            echo "[rva] Pulsar ready."
            return 0
        fi
        attempt=$((attempt + 1))
        printf "\r[rva] Pulsar not ready yet... %ds" $((attempt * 3))
        sleep 3
    done
    echo ""
    echo "[rva] WARNING: Pulsar not ready after 120s — Vision will retry on its own."
}

# ── stop ──────────────────────────────────────────────────────────────────────

if [[ "${1:-}" == "stop" ]]; then
    echo "[rva] Stopping tmux session..."
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    echo "[rva] Stopping Docker stack..."
    docker compose --project-directory "$PROJECT_ROOT" down
    echo "[rva] Done."
    exit 0
fi

# ── guard: tmux required ──────────────────────────────────────────────────────

if ! command -v tmux &>/dev/null; then
    echo "ERROR: tmux not installed. Run: sudo apt install tmux"
    exit 1
fi

# ── guard: session already running → attach ───────────────────────────────────

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "[rva] Session '$SESSION' already exists — attaching."
    exec tmux attach -t "$SESSION"
fi

cd "$PROJECT_ROOT"

# ── 1. Docker stack ───────────────────────────────────────────────────────────

echo "[rva] Checking Docker stack..."

if _stack_healthy; then
    echo "[rva] All core containers are running — skipping docker compose up."
    RUNNING_JOBS=$(_flink_running_jobs)
    echo "[rva] Flink running jobs: $RUNNING_JOBS"
    if [[ "$RUNNING_JOBS" -eq 0 ]]; then
        echo "[rva] WARNING: No Flink jobs running. To resubmit:"
        echo "[rva]   docker compose run --rm flink-job-submitter"
    fi
else
    echo "[rva] Starting Docker stack..."
    docker compose up -d
    if [[ $? -ne 0 ]]; then
        echo "[rva] ERROR: docker compose up failed. Check docker-compose.yml."
        exit 1
    fi

    # Wait for Pulsar before starting Vision (Pulsar is slowest)
    _wait_pulsar
fi

# ── 2. tmux session: 4 windows ────────────────────────────────────────────────
#
#   0: docker (logs)  |  1: vision
#   ─────────────────────────────
#   2: api            |  3: frontend

echo "[rva] Creating tmux session '$SESSION'..."

tmux new-session -d -s "$SESSION" -n "docker"
tmux new-window  -t "$SESSION"    -n "vision"
tmux new-window  -t "$SESSION"    -n "api"
tmux new-window  -t "$SESSION"    -n "frontend"

# window 0 — docker logs (all containers)
tmux send-keys -t "$SESSION:docker" \
    "cd '$PROJECT_ROOT' && docker compose logs -f --tail=50" Enter

# window 1 — Vision pipeline
tmux send-keys -t "$SESSION:vision" \
    "cd '$PROJECT_ROOT' && uv run --package rva-vision python services/vision/main.py" Enter

# window 2 — FastAPI
tmux send-keys -t "$SESSION:api" \
    "cd '$PROJECT_ROOT' && uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000" Enter

# window 3 — React frontend
tmux send-keys -t "$SESSION:frontend" \
    "cd '$PROJECT_ROOT/frontend' && npm run dev" Enter

# ── 3. Attach ─────────────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  RVA dev stack started — tmux session    ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Ctrl+b → 0   docker logs               ║"
echo "║  Ctrl+b → 1   vision (camera pipeline)  ║"
echo "║  Ctrl+b → 2   api   (FastAPI :8000)     ║"
echo "║  Ctrl+b → 3   frontend (React :5173)    ║"
echo "║  Ctrl+b → d   detach (stack keeps running)║"
echo "║  ./scripts/dev-start.sh stop  → stop all║"
echo "╚══════════════════════════════════════════╝"
echo ""

exec tmux attach -t "$SESSION:vision"
