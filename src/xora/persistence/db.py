from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from xora.config.settings import get_settings

_engine: Engine | None = None
_HOSTS = (
    None,
    "xora_postgres",
    "postgres",
    "xora_trade_ai-postgres",
    "host.docker.internal",
    "172.17.0.1",
    "127.0.0.1",
)


def _urls() -> list[str]:
    base = get_settings().database_url
    parsed = urlparse(base.replace("postgresql+psycopg", "http"))
    out: list[str] = []
    seen: set[str] = set()
    for host in _HOSTS:
        if host is None:
            url = base
        else:
            replaced = parsed._replace(netloc=f"{parsed.username}:{parsed.password}@{host}:{parsed.port or 5432}")
            url = urlunparse(replaced).replace("http://", "postgresql+psycopg://", 1)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(_urls()[0], pool_pre_ping=True, future=True)
    return _engine


def wait_for_db(attempts: int = 8, delay: float = 1.0) -> None:
    global _engine
    last = None
    for url in _urls():
        _engine = create_engine(url, pool_pre_ping=True, future=True)
        for _ in range(attempts):
            try:
                with _engine.connect() as conn:
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
