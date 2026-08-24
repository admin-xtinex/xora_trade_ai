from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from xora.api.v1 import router
from xora.config.settings import get_settings
from xora.persistence.db import apply_schema


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    apply_schema()
    yield


app = FastAPI(title="XORA Prediction AI", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/")
def root() -> dict:
    return {
        "name": "XORA Prediction AI",
        "docs": "/docs",
        "health": "/api/v1/health",
        "run_cycle": "POST /api/v1/admin/cycles",
    }
