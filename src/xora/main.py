from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from xora.api.v1 import router
from xora.api.ws import router as ws_router
from xora.config.settings import get_settings
from xora.persistence.db import apply_schema

UI_DIR = Path(__file__).resolve().parents[2] / "ui"
if not UI_DIR.exists():
    UI_DIR = Path("/app/ui")

log = logging.getLogger("xora.api")


def _schema_later() -> None:
    try:
        apply_schema()
        log.info("schema ready")
    except Exception:
        log.exception("schema apply failed; UI still up")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    threading.Thread(target=_schema_later, daemon=True).start()
    yield


app = FastAPI(title="XORA Prediction AI", version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.include_router(ws_router)

if UI_DIR.exists():
    app.mount("/static", StaticFiles(directory=UI_DIR), name="static")


@app.get("/")
def root():
    index = UI_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return {"name": "XORA Prediction AI", "docs": "/docs"}
