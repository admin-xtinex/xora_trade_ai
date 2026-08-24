from __future__ import annotations

import time
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


def wait_for_db(attempts: int = 30, delay: float = 2.0) -> None:
    last = None
    for _ in range(attempts):
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(delay)
    raise RuntimeError(f"database not reachable: {last}") from last


def apply_schema() -> None:
    wait_for_db()
    settings = get_settings()
    schema_dir = settings.root / "schema"
    if not schema_dir.exists():
        schema_dir = Path("/app/schema")
    files = sorted(schema_dir.glob("*.sql"))
    with get_engine().begin() as conn:
        for sql_path in files:
            raw = sql_path.read_text()
            for statement in [part.strip() for part in raw.split(";") if part.strip()]:
                conn.execute(text(statement))
