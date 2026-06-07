#!/usr/bin/env bash
# dev-start.sh — Start the full RVA dev stack in a named tmux session.
#
# Usage:
#   ./scripts/dev-start.sh          # start everything
#   ./scripts/dev-start.sh stop     # kill the tmux session + docker stack
#
# Attach anytime:   tmux attach -t rva
# Kill session:     tmux kill-session -t rva
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="rva"

# ── stop ────────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "stop" ]]; then
  echo "[rva] Stopping..."
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  docker compose --project-directory "$PROJECT_ROOT" down
  echo "[rva] All services stopped."
  exit 0
fi

# ── guard: tmux required ─────────────────────────────────────────────────────
if ! command -v tmux &>/dev/null; then
  echo "ERROR: tmux is not installed. Run: sudo apt install tmux"
  exit 1
fi

# ── guard: already running ───────────────────────────────────────────────────
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "[rva] Session '$SESSION' already exists. Attaching..."
  tmux attach -t "$SESSION"
  exit 0
fi

cd "$PROJECT_ROOT"

# ── 1. Docker stack ──────────────────────────────────────────────────────────
echo "[rva] Starting Docker stack..."
docker compose up -d

echo "[rva] Waiting 15s for services to be healthy..."
sleep 15

# ── 2. tmux session layout ───────────────────────────────────────────────────
#
#  ┌──────────────────────┬───────────────────────┐
#  │  0: vision           │  1: api               │
#  ├──────────────────────┴───────────────────────┤
#  │  2: frontend                                  │
#  └───────────────────────────────────────────────┘

tmux new-session  -d -s "$SESSION" -n "vision"
tmux new-window   -t "$SESSION" -n "api"
tmux new-window   -t "$SESSION" -n "frontend"

# window 0 — Vision
tmux send-keys -t "$SESSION:vision" \
  "cd $PROJECT_ROOT && uv run --package rva-vision python services/vision/main.py" Enter

# window 1 — API
tmux send-keys -t "$SESSION:api" \
  "cd $PROJECT_ROOT && uv run --package rva-api uvicorn rva_api.main:app --reload --port 8000" Enter

# window 2 — Frontend
tmux send-keys -t "$SESSION:frontend" \
  "cd $PROJECT_ROOT/frontend && npm run dev" Enter

# ── 3. Attach ────────────────────────────────────────────────────────────────
echo ""
echo "[rva] Stack is up. Attaching to tmux session '$SESSION'..."
echo "  Switch windows : Ctrl+b  then  0 / 1 / 2"
echo "  Detach (keep running): Ctrl+b  then  d"
echo "  Stop everything: ./scripts/dev-start.sh stop"
echo ""

tmux attach -t "$SESSION"
