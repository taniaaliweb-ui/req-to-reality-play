#!/usr/bin/env bash
# Double-click in Finder to start LifeSpan. Close the Terminal window (or Ctrl+C) to stop.
cd "$(dirname "$0")"
[ -x backend/.venv/bin/python ] || ./scripts/setup-macos.sh
exec ./scripts/start-local.sh
