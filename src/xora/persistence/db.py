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
    schema_dir = settings.root / "schema"
    if not schema_dir.exists():
        schema_dir = Path("/app/schema")
    files = sorted(schema_dir.glob("*.sql"))
    with get_engine().begin() as conn:
        for sql_path in files:
            raw = sql_path.read_text()
            for statement in [part.strip() for part in raw.split(";") if part.strip()]:
                conn.execute(text(statement))
