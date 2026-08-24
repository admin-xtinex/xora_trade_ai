from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from xora.application.analysis import build_analysis, build_trade_analysis
from xora.application.pipeline import PredictionPlatform
from xora.persistence.queries import Analytics
from xora.persistence.store import Store

router = APIRouter(prefix="/api/v1")
_platform: PredictionPlatform | None = None


def platform() -> PredictionPlatform:
    global _platform
    if _platform is None:
        _platform = PredictionPlatform()
    return _platform


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "xora-prediction-ai",
        "timeframe": "15m",
        "margin": 10,
        "leverage": 15,
        "warmup_seconds": 300,
    }


@router.get("/session")
def session() -> dict:
    return Analytics().live_snapshot()


@router.get("/coins")
def coins(min_win: float | None = Query(default=None), min_samples: int = Query(default=0)) -> list[dict]:
    return Analytics().coin_stats(min_hit_rate=min_win, min_samples=min_samples)


@router.get("/trades")
def trades(status: str | None = Query(default=None)) -> list[dict]:
    return Analytics().trades(status=status)


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
    store = Store()
    item = store.prediction_detail(prediction_id)
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
