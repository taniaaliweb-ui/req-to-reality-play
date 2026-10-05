"""Offline transport for tests: serves recorded World Bank JSON from a directory.
File name = path with '/' replaced by '_' plus '.json' (e.g. country_IN_indicator_FP.CPI.TOTL.json).
A file named '<name>.status' containing e.g. 500 forces that HTTP status; 'TIMEOUT' raises a timeout."""
from __future__ import annotations

import json
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
        data = json.loads(f.read_text())
        date = request.url.params.get("date")  # raw ":" survives parsing
        if date and len(data) > 1 and isinstance(data[1], list):
            y0, _, y1 = date.partition(":")
            data[1] = [r for r in data[1] if int(y0) <= int(r["date"]) <= int(y1 or y0)]
        return httpx.Response(200, json=data)

    return httpx.MockTransport(handler)


def ilo_fixture_transport(directory: str) -> httpx.MockTransport:
    """Serves recorded ILOSTAT SDMX-CSV files named <DATAFLOW>.csv, filtered like the real service."""
    import csv
    import io

    root = Path(directory)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/dataflow/" in path:
            return httpx.Response(200, text="<Structure/>")
        parts = path.split("/data/", 1)[1].split("/")
        flow = parts[0].split(",")[1]
        status_file = root / f"{flow}.status"
        if status_file.exists():
            st = status_file.read_text().strip()
            if st == "TIMEOUT":
                raise httpx.ReadTimeout("fixture timeout", request=request)
            return httpx.Response(int(st), text="error")
        f = root / f"{flow}.csv"
        if not f.exists():
            return httpx.Response(404, text="Could not find Dataflow and/or DSD related with this data request")
        countries = set(parts[1].split(".")[0].split("+")) if len(parts) > 1 else set()
        y0 = int(request.url.params.get("startPeriod", "0"))
        y1 = int(request.url.params.get("endPeriod", "9999"))
        rows = list(csv.reader(io.StringIO(f.read_text())))
        h = rows[0]
        ai, ti = h.index("REF_AREA"), h.index("TIME_PERIOD")
        keep = [r for r in rows[1:] if (not countries or r[ai] in countries) and y0 <= int(r[ti][:4]) <= y1]
        if not keep:
            return httpx.Response(404, text="NoResultsFound")
        buf = io.StringIO()
        csv.writer(buf).writerows([h, *keep])
        return httpx.Response(200, text=buf.getvalue())

    return httpx.MockTransport(handler)
