from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from xora.config.settings import get_settings

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    return _engine


def apply_schema() -> None:
    settings = get_settings()
    sql_path = settings.root / "schema" / "001_init.sql"
    if not sql_path.exists():
        sql_path = Path("/app/schema/001_init.sql")
    raw = sql_path.read_text()
    with get_engine().begin() as conn:
        conn.execute(text(raw))
