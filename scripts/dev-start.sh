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
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="rva"
CORE_SERVICES=("flink-jobmanager" "flink-taskmanager" "pulsar-broker" "redis" "iceberg-rest")

# ── helpers ───────────────────────────────────────────────────────────────────

_container_running() {
    docker ps --filter "name=^$1$" --filter "status=running" -q 2>/dev/null | grep -q .
}

_stack_healthy() {
    for svc in "${CORE_SERVICES[@]}"; do
        _container_running "$svc" || return 1
    done
    return 0
}

_flink_running_jobs() {
    curl -s http://localhost:8081/jobs 2>/dev/null \
        | python3 -c "
import json,sys
try: print(sum(1 for j in json.load(sys.stdin)['jobs'] if j['status']=='RUNNING'))
except: print(0)
" 2>/dev/null || echo 0
}

_wait_pulsar() {
    echo "[rva] Waiting for Pulsar broker to be ready..."
    local attempt=0
    local max=40   # 40 x 3s = 120s max
    while [ $attempt -lt $max ]; do
        if docker exec pulsar-broker bin/pulsar-admin brokers healthcheck \
               --url http://localhost:8080 &>/dev/null 2>&1; then
            echo "[rva] Pulsar is ready."
            return 0
        fi
        attempt=$((attempt + 1))
        printf "\r[rva] Pulsar not ready yet (%ds)..." $((attempt * 3))
        sleep 3
    done
    echo ""
    echo "[rva] WARNING: Pulsar did not become ready after 120s. Vision may retry on its own."
}

# ── stop ──────────────────────────────────────────────────────────────────────

if [[ "${1:-}" == "stop" ]]; then
    echo "[rva] Stopping tmux session..."
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    echo "[rva] Stopping Docker stack..."
    docker compose --project-directory "$PROJECT_ROOT" down
    echo "[rva] All services stopped."
    exit 0
fi

# ── guard: tmux required ──────────────────────────────────────────────────────

if ! command -v tmux &>/dev/null; then
    echo "ERROR: tmux is not installed. Run: sudo apt install tmux"
    exit 1
fi

# ── guard: session already running → just attach ──────────────────────────────

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "[rva] Session '$SESSION' already exists — attaching."
    tmux attach -t "$SESSION"
    exit 0
fi

cd "$PROJECT_ROOT"

# ── 1. Docker stack ───────────────────────────────────────────────────────────

if _stack_healthy; then
    echo "[rva] Docker stack already healthy — skipping docker compose up."

    RUNNING_JOBS=$(_flink_running_jobs)
    if [[ "$RUNNING_JOBS" -gt 0 ]]; then
        echo "[rva] Flink has $RUNNING_JOBS running job(s) — skipping submission."
    else
        echo "[rva] WARNING: Flink has 0 running jobs."
        echo "[rva] To resubmit: docker compose run --rm flink-job-submitter"
    fi
else
    echo "[rva] Starting Docker stack (excluding job-submitter)..."
    docker compose up -d --scale flink-job-submitter=0

    # Wait for Pulsar specifically — it's the slowest and Vision needs it first
    _wait_pulsar

    # Submit Flink jobs only if none are running
    RUNNING_JOBS=$(_flink_running_jobs)
    if [[ "$RUNNING_JOBS" -eq 0 ]]; then
        echo "[rva] Submitting Flink jobs..."
        docker compose run --rm flink-job-submitter
    else
        echo "[rva] Flink already has $RUNNING_JOBS job(s) — skipping submission."
    fi
fi

# ── 2. tmux session: 4 windows ────────────────────────────────────────────────
#
#  ┌───────────────────┬──────────────────────┐
#  │  0: docker        │  1: vision           │
#  ├───────────────────┼──────────────────────┤
#  │  2: api           │  3: frontend         │
#  └───────────────────┴──────────────────────┘

tmux new-session  -d -s "$SESSION" -n "docker"
tmux new-window   -t "$SESSION" -n "vision"
tmux new-window   -t "$SESSION" -n "api"
tmux new-window   -t "$SESSION" -n "frontend"

# window 0 — docker logs (theo dõi toàn bộ stack)
tmux send-keys -t "$SESSION:docker" \
    "cd $PROJECT_ROOT && docker compose logs -f --tail=50" Enter

# window 1 — Vision
tmux send-keys -t "$SESSION:vision" \
    "cd $PROJECT_ROOT && uv run --package rva-vision python services/vision/main.py" Enter

# window 2 — API
tmux send-keys -t "$SESSION:api" \
    "cd $PROJECT_ROOT && uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000" Enter

# window 3 — Frontend
tmux send-keys -t "$SESSION:frontend" \
    "cd $PROJECT_ROOT/frontend && npm run dev" Enter

# ── 3. Attach vào window docker trước để thấy trạng thái ─────────────────────

echo ""
echo "[rva] Stack is up. Attaching to tmux session '$SESSION'..."
echo "  Ctrl+b → 0  docker logs     (theo dõi containers)"
echo "  Ctrl+b → 1  vision          (camera pipeline)"
echo "  Ctrl+b → 2  api             (FastAPI)"
echo "  Ctrl+b → 3  frontend        (React dev server)"
echo "  Ctrl+b → d  detach          (giữ stack chạy)"
echo "  ./scripts/dev-start.sh stop (dừng tất cả)"
echo ""

# Attach vào window "vision" (window 1) để thấy pipeline ngay
tmux attach -t "$SESSION:vision"
