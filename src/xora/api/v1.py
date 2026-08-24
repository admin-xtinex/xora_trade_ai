from __future__ import annotations

from fastapi import APIRouter, HTTPException

from xora.application.pipeline import PredictionPlatform
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
    return {"status": "ok", "service": "xora-prediction-ai"}


@router.get("/coins")
def coins() -> list[dict]:
    return Store().list_rows("coins")


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


@router.get("/validations")
def validations() -> list[dict]:
    return Store().list_rows("validations")


@router.get("/scores")
def scores() -> list[dict]:
    return Store().list_rows("scores")


@router.get("/qualified-coins")
def qualified() -> list[dict]:
    return Store().list_rows("qualified")


@router.get("/modules")
def modules() -> list[dict]:
    return Store().list_rows("modules")


@router.post("/admin/cycles")
def run_cycle() -> dict:
    return platform().run_cycle()
