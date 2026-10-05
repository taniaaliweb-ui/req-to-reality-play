"""Offline transport for tests: serves recorded World Bank JSON from a directory.
File name = path with '/' replaced by '_' plus '.json' (e.g. country_IN_indicator_FP.CPI.TOTL.json).
A file named '<name>.status' containing e.g. 500 forces that HTTP status; 'TIMEOUT' raises a timeout."""
from __future__ import annotations

from pathlib import Path

import httpx


def fixture_transport(directory: str) -> httpx.MockTransport:
    root = Path(directory)

    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.removeprefix("/v2/").strip("/").replace("/", "_")
        status_file = root / f"{name}.status"
        if status_file.exists():
            st = status_file.read_text().strip()
            if st == "TIMEOUT":
                raise httpx.ReadTimeout("fixture timeout", request=request)
            return httpx.Response(int(st), text="error")
        f = root / f"{name}.json"
        if not f.exists():
            return httpx.Response(200, json=[{"message": [{"id": "120", "key": "Invalid value", "value": "The provided parameter value is not valid"}]}])
        return httpx.Response(200, text=f.read_text(), headers={"content-type": "application/json"})

    return httpx.MockTransport(handler)
