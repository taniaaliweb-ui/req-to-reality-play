#!/usr/bin/env bash
# One-time setup for LifeSpan on macOS (Apple Silicon). No Docker required.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v python3 >/dev/null || { echo "Python 3 is required: https://www.python.org/downloads/macos/"; exit 1; }
command -v npm >/dev/null || { echo "Node.js (with npm) is required: https://nodejs.org/"; exit 1; }
echo "==> Creating Python virtual environment (backend/.venv)"
python3 -m venv backend/.venv
backend/.venv/bin/pip install --upgrade pip >/dev/null
echo "==> Installing backend dependencies"
backend/.venv/bin/pip install -r backend/requirements.txt
echo "==> Installing frontend dependencies"
npm install
echo "==> Setup complete. Start LifeSpan with: ./scripts/start-local.sh"
