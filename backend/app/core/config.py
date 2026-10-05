"""Backend configuration. Values can be overridden with environment variables."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("LIFESPAN_DATA_DIR", BACKEND_DIR / "data"))
DATABASE_URL = os.environ.get("LIFESPAN_DATABASE_URL", f"sqlite:///{DATA_DIR / 'lifespan.db'}")

HOST = os.environ.get("LIFESPAN_HOST", "127.0.0.1")
PORT = int(os.environ.get("LIFESPAN_PORT", "8000"))

# Local development origins only: http://localhost:<port> and http://127.0.0.1:<port>
CORS_ORIGIN_REGEX = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"

SEED_DEMO = os.environ.get("LIFESPAN_SEED_DEMO", "1") == "1"
SERVICE_NAME = "lifespan-backend"
API_PREFIX = "/api/v1"
