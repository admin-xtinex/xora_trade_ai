from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from xora.application.analysis import build_analysis, build_trade_analysis
from xora.application.pipeline import PredictionPlatform
from xora.engines.registry import EngineRegistry
from xora.persistence.queries import Analytics
from xora.persistence.store import Store

router = APIRouter(prefix="/api/v1")
_platform: PredictionPlatform | None = None


def platform() -> PredictionPlatform:
    global _platform
    if _platform is None:
        _platform = PredictionPlatform()
    return _platform


class EngineSelect(BaseModel):
    keys: list[str]


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "timezone": "Asia/Kolkata", "timeframe": "15m"}


@router.get("/session")
def session() -> dict:
    snap = Analytics().live_snapshot()
    registry = EngineRegistry()
    snap["engines"] = registry.all_meta()
    snap["active_engines"] = registry.active_keys()
    return snap


@router.post("/admin/start")
def start_trading() -> dict:
    return platform().start_trading()


@router.get("/engines")
def engines() -> dict:
    registry = EngineRegistry()
    return {"engines": registry.all_meta(), "active": registry.active_keys()}


@router.post("/engines/active")
def set_engines(body: EngineSelect) -> dict:
    registry = EngineRegistry()
    return {"active": registry.set_active(body.keys), "engines": registry.all_meta()}


@router.get("/coins")
def coins(min_win: float | None = Query(default=None), min_samples: int = Query(default=0)) -> list[dict]:
    return Analytics().coin_stats(min_hit_rate=min_win, min_samples=min_samples)


@router.get("/trades")
def trades(status: str | None = Query(default=None), engine: str | None = Query(default=None)) -> list[dict]:
    return Analytics().trades(status=status, engine=engine)


@router.get("/trades/{trade_id}")
def trade(trade_id: str) -> dict:
    item = Analytics().trade_detail(trade_id)
    if not item:
        raise HTTPException(status_code=404, detail="trade not found")
    return build_trade_analysis(item)


@router.get("/predictions")
def predictions() -> list[dict]:
    return Store().list_rows("predictions")


@router.get("/predictions/{prediction_id}")
def prediction_detail(prediction_id: str) -> dict:
    item = Store().prediction_detail(prediction_id)
    if not item:
        raise HTTPException(status_code=404, detail="prediction not found")
    return item


@router.get("/predictions/{prediction_id}/analysis")
def prediction_analysis(prediction_id: str) -> dict:
    item = Store().prediction_detail(prediction_id)
    if not item:
        raise HTTPException(status_code=404, detail="prediction not found")
    return build_analysis(item)


@router.get("/validations")
def validations() -> list[dict]:
    return Store().list_rows("validations")


@router.get("/modules")
def modules() -> list[dict]:
    return Store().list_rows("modules")


@router.post("/admin/cycles")
def run_cycle() -> dict:
    return platform().run_cycle()
