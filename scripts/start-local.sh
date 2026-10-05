#!/usr/bin/env bash
# Starts LifeSpan backend (127.0.0.1:8000) and frontend (127.0.0.1:3000). Press Ctrl+C to stop both.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -x backend/.venv/bin/python ] || { echo "Run ./scripts/setup-macos.sh first."; exit 1; }

cleanup() { echo; echo "Stopping LifeSpan…"; kill "${BACK_PID:-}" "${FRONT_PID:-}" 2>/dev/null || true; wait 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "==> Starting backend on http://127.0.0.1:8000"
( cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 ) &
BACK_PID=$!

for _ in $(seq 1 50); do curl -sf http://127.0.0.1:8000/api/v1/health >/dev/null && break; sleep 0.2; done

echo "==> Starting frontend on http://127.0.0.1:3000"
VITE_LIFESPAN_DATA_MODE=backend VITE_LIFESPAN_API_URL=http://127.0.0.1:8000 npx vite dev --host 127.0.0.1 --port 3000 --strictPort &
FRONT_PID=$!

sleep 3
open "http://127.0.0.1:3000" 2>/dev/null || true
echo "==> LifeSpan running. Press Ctrl+C in this window to stop."
wait
