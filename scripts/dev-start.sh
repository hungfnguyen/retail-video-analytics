#!/usr/bin/env bash
# dev-start.sh — Start the full RVA dev stack in a named tmux session.
#
# Usage:
#   ./scripts/dev-start.sh          # start everything (idempotent)
#   ./scripts/dev-start.sh stop     # kill the tmux session + docker stack
#
# Attach anytime:     tmux attach -t rva
# Switch windows:     Ctrl+b then 0 / 1 / 2
# Detach (keep running): Ctrl+b then d
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="rva"

# Core containers that must be running for the stack to be considered healthy.
# flink-job-submitter is intentionally excluded — it's a one-shot init container.
CORE_SERVICES=("flink-jobmanager" "flink-taskmanager" "pulsar-broker" "redis" "iceberg-rest")

# ── helpers ──────────────────────────────────────────────────────────────────

_container_running() {
    docker ps --filter "name=^$1$" --filter "status=running" -q 2>/dev/null | grep -q .
}

_stack_healthy() {
    for svc in "${CORE_SERVICES[@]}"; do
        if ! _container_running "$svc"; then
            return 1
        fi
    done
    return 0
}

_flink_running_jobs() {
    curl -s http://localhost:8081/jobs 2>/dev/null \
        | python3 -c "
import json,sys
try:
    print(sum(1 for j in json.load(sys.stdin)['jobs'] if j['status']=='RUNNING'))
except: print(0)
" 2>/dev/null || echo 0
}

# ── stop ─────────────────────────────────────────────────────────────────────

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

# ── guard: session already running → just attach ─────────────────────────────

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "[rva] Session '$SESSION' already exists — attaching."
    tmux attach -t "$SESSION"
    exit 0
fi

cd "$PROJECT_ROOT"

# ── 1. Docker stack (idempotent) ──────────────────────────────────────────────

if _stack_healthy; then
    echo "[rva] Docker stack already healthy — skipping docker compose up."
    echo "[rva]   Running containers: ${CORE_SERVICES[*]}"

    RUNNING_JOBS=$(_flink_running_jobs)
    if [[ "$RUNNING_JOBS" -gt 0 ]]; then
        echo "[rva] Flink has $RUNNING_JOBS running job(s) — skipping job submission."
    else
        echo "[rva] WARNING: Flink has 0 running jobs."
        echo "[rva] To resubmit: docker compose run --rm flink-job-submitter"
    fi
else
    echo "[rva] Starting Docker stack..."
    # Exclude flink-job-submitter from initial up; start it only after
    # JobManager is healthy to avoid duplicate submissions on re-runs.
    docker compose up -d --scale flink-job-submitter=0

    echo "[rva] Waiting 20s for services to become healthy..."
    sleep 20

    # Submit Flink jobs only if none are running yet
    RUNNING_JOBS=$(_flink_running_jobs)
    if [[ "$RUNNING_JOBS" -eq 0 ]]; then
        echo "[rva] Submitting Flink jobs..."
        docker compose run --rm flink-job-submitter
    else
        echo "[rva] Flink already has $RUNNING_JOBS job(s) — skipping submission."
    fi
fi

# ── 2. tmux session with 3 windows ───────────────────────────────────────────
#
#  ┌──────────────────────┬───────────────────────┐
#  │  0: vision           │  1: api               │
#  ├──────────────────────┴───────────────────────┤
#  │  2: frontend                                  │
#  └───────────────────────────────────────────────┘

tmux new-session  -d -s "$SESSION" -n "vision"
tmux new-window   -t "$SESSION" -n "api"
tmux new-window   -t "$SESSION" -n "frontend"

tmux send-keys -t "$SESSION:vision" \
    "cd $PROJECT_ROOT && uv run --package rva-vision python services/vision/main.py" Enter

tmux send-keys -t "$SESSION:api" \
    "cd $PROJECT_ROOT && uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000" Enter

tmux send-keys -t "$SESSION:frontend" \
    "cd $PROJECT_ROOT/frontend && npm run dev" Enter

# ── 3. Attach ─────────────────────────────────────────────────────────────────

echo ""
echo "[rva] Stack is up. Attaching to tmux session '$SESSION'..."
echo "  Switch windows      : Ctrl+b → 0 (vision) / 1 (api) / 2 (frontend)"
echo "  Detach (keep alive) : Ctrl+b → d"
echo "  Stop everything     : ./scripts/dev-start.sh stop"
echo ""

tmux attach -t "$SESSION"
