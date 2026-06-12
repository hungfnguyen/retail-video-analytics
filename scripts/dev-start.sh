#!/usr/bin/env bash
# dev-start.sh — Start RVA services in a named tmux session.
#
# NOTE: Docker stack must be started manually before running this script.
#
# Usage:
#   ./scripts/dev-start.sh          # start tmux session (idempotent)
#   ./scripts/dev-start.sh stop     # kill the tmux session
#
# Attach anytime:          tmux attach -t rva
# Switch windows:          Ctrl+b then 0 / 1 / 2 / 3
# Detach (keep running):   Ctrl+b then d
set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="rva"

# ── stop ──────────────────────────────────────────────────────────────────────

if [[ "${1:-}" == "stop" ]]; then
    echo "[rva] Stopping tmux session '$SESSION'..."
    tmux kill-session -t "$SESSION" 2>/dev/null && echo "[rva] Done." || echo "[rva] Session not found."
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

# ── tmux session: 4 windows ───────────────────────────────────────────────────
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
# Source .env for S3/boto3 credentials, then override Docker-internal hostnames
# with localhost equivalents for host-side processes.
# Wrapped in `bash -c` so the bash-only `set -a` / `source .env` syntax works
# even when the tmux window shell is fish (or any non-bash shell).
tmux send-keys -t "$SESSION:api" \
    "cd '$PROJECT_ROOT' && bash -c 'set -a; source .env; set +a; export REDIS_HOST=localhost REDIS_PORT=16379 PULSAR_SERVICE_URL=pulsar://localhost:6650; exec uv run --package rva-api uvicorn rva_api.main:app --workers 4 --port 8000'" Enter

# window 3 — React frontend
# Vite needs Node 20.19+/22.12+. nvm is bash-based and is NOT loaded by fish,
# so a fish tmux window falls back to the old system node. Load nvm inside
# `bash -c` and select node 20 before launching the dev server.
tmux send-keys -t "$SESSION:frontend" \
    "cd '$PROJECT_ROOT/frontend' && bash -c '. \"\$HOME/.nvm/nvm.sh\"; nvm use 20 >/dev/null 2>&1 || nvm use --lts >/dev/null 2>&1; exec npm run dev'" Enter

# ── attach ────────────────────────────────────────────────────────────────────

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
