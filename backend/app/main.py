"""LifeSpan backend entry point. Run: uvicorn app.main:app --host 127.0.0.1 --port 8000"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import data, labor, life, resources, system
from app.core.config import API_PREFIX, CORS_ORIGIN_REGEX, SEED_DEMO
from app.db.database import SessionLocal, ping
from app.db.migrate import upgrade_to_head
from app.seed.demo_episode import seed_demo
from app.seed.life_registry import seed_life_registry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("lifespan")


@asynccontextmanager
async def lifespan(_: FastAPI):
    upgrade_to_head()
    log.info("LifeSpan backend started")
    log.info("Database %s", "connected" if ping() else "UNAVAILABLE")
    with SessionLocal() as db:
        seed_life_registry(db)  # reference registry (unverified events/policies), idempotent
        if SEED_DEMO:
            seed_demo(db)
    yield


app = FastAPI(title="LifeSpan Backend", version="0.5.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origin_regex=CORS_ORIGIN_REGEX, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def access_log(request: Request, call_next):
    t = time.perf_counter()
    response = await call_next(request)
    log.info("%s %s %s %.0fms", request.method, request.url.path, response.status_code, (time.perf_counter() - t) * 1000)
    return response


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.exception("Unhandled error: %s", exc)  # full trace in server log only
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(system.router, prefix=API_PREFIX)
app.include_router(resources.router, prefix=API_PREFIX)
app.include_router(data.router, prefix=API_PREFIX)
app.include_router(labor.router, prefix=API_PREFIX)
app.include_router(life.router, prefix=API_PREFIX)
