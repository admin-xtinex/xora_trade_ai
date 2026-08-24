from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from xora.application.analysis import attach_validation, build_analysis
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
    return {"status": "ok", "service": "xora-prediction-ai", "timeframe": "5m", "transport": "http+websocket"}


@router.get("/coins")
def coins(min_win: float | None = Query(default=None), min_samples: int = Query(default=1)) -> list[dict]:
    return Analytics().coin_stats(min_hit_rate=min_win, min_samples=min_samples)


@router.get("/coins/{symbol}/setups")
def coin_setups(symbol: str) -> list[dict]:
    return Analytics().coin_predictions(symbol)


@router.get("/snapshots")
def snapshots() -> list[dict]:
    return Store().list_rows("snapshots")


@router.get("/features")
def features() -> list[dict]:
    return Store().list_rows("features")


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
    return build_analysis(item, attach_validation(store, prediction_id))


@router.get("/validations")
def validations() -> list[dict]:
    return Store().list_rows("validations")


@router.get("/scores")
def scores() -> list[dict]:
    return Store().list_rows("scores")


@router.get("/qualified-coins")
def qualified(min_win: float | None = Query(default=None)) -> list[dict]:
    rows = Analytics().coin_stats(min_hit_rate=min_win, min_samples=1)
    return rows


@router.get("/modules")
def modules() -> list[dict]:
    return Store().list_rows("modules")


@router.post("/admin/cycles")
def run_cycle() -> dict:
    return platform().run_cycle()
