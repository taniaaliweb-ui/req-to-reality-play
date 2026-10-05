"""Tests run the REAL server (uvicorn subprocess) against a temporary SQLite file,
so 'restart backend' genuinely stops and starts the process."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

BACKEND = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.port = _free_port()
        self.proc: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/api/v1"

    def start(self):
        env = {**os.environ, "LIFESPAN_DATA_DIR": str(self.data_dir), "PYTHONPATH": str(BACKEND)}
        env.pop("LIFESPAN_DATABASE_URL", None)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            try:
                if httpx.get(self.url + "/health", timeout=0.5).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise RuntimeError("backend did not start")

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=10)
            self.proc = None

    def restart(self):
        self.stop()
        self.start()

    def client(self) -> httpx.Client:
        return httpx.Client(base_url=self.url, timeout=10)


@pytest.fixture()
def server(tmp_path):
    srv = Server(tmp_path)
    srv.start()
    yield srv
    srv.stop()
