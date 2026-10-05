"""Runs Alembic migrations programmatically at startup."""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import BACKEND_DIR, DATA_DIR, DATABASE_URL


def alembic_config(url: str = DATABASE_URL) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def upgrade_to_head(url: str = DATABASE_URL) -> None:
    if url.startswith("sqlite:///"):
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True)
    command.upgrade(alembic_config(url), "head")
