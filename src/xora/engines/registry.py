from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from xora.config.settings import get_settings
from xora.domain.enums import Direction
from xora.domain.models import DecisionResult, FeatureResult, ModuleContribution
from xora.persistence.db import get_engine
from sqlalchemy import text


@dataclass
class EngineSpec:
    key: str
    name: str
    description: str
    tp_pct: float
    sl_pct: float
    enter_threshold: float
    weights: dict[str, float]


class TradingEngine:
    def __init__(self, spec: EngineSpec) -> None:
        self.spec = spec
        self.key = spec.key
        self.name = spec.name

    def decide(self, results: list[FeatureResult], fallback_change: float | None = None) -> DecisionResult:
        contributions: list[ModuleContribution] = []
        score = 0.0
        weight_sum = 0.0
        atr_pct = None
        for result in results:
            weight = float(self.spec.weights.get(result.module_key, 0.0))
            conf = result.confidence or 0.0
            signed = 0.0
            if result.direction_hint == Direction.UP:
                signed = weight * conf
            elif result.direction_hint == Direction.DOWN:
                signed = -weight * conf
            score += signed
            weight_sum += abs(weight)
            if "atr_pct" in result.features:
                atr_pct = float(result.features["atr_pct"])
            contributions.append(
                ModuleContribution(
                    module_name=result.module_key,
                    module_version=result.module_version,
                    weight=weight,
                    confidence=result.confidence,
                    contribution=signed,
                    decision=result.direction_hint.value if result.direction_hint else None,
                    raw_features=result.features,
                )
            )
        threshold = self.spec.enter_threshold
        if score > threshold:
            direction = Direction.UP
            forced = False
        elif score < -threshold:
            direction = Direction.DOWN
            forced = False
        else:
            forced = True
            if score > 0:
                direction = Direction.UP
            elif score < 0:
                direction = Direction.DOWN
            elif (fallback_change or 0) >= 0:
                direction = Direction.UP
            else:
                direction = Direction.DOWN
        confidence = min(0.95, max(abs(score) / max(weight_sum, 1e-6), 0.15 if forced else 0.0))
        return DecisionResult(
            direction=direction,
            confidence=confidence,
            score=score,
            magnitude=atr_pct * 1.5 if atr_pct is not None else None,
            market_regime="volatile" if (atr_pct or 0) > 0.02 else "normal",
            contributions=contributions,
            metadata={
                "engine": self.key,
                "engine_name": self.name,
                "forced": forced,
                "tp_pct": self.spec.tp_pct,
                "sl_pct": self.spec.sl_pct,
            },
        )

    def levels(self, side: str, entry: float) -> tuple[float, float]:
        tp_pct, sl_pct = self.spec.tp_pct, self.spec.sl_pct
        if side == "DOWN":
            return entry * (1 - tp_pct), entry * (1 + sl_pct)
        return entry * (1 + tp_pct), entry * (1 - sl_pct)

    def should_exit(self, trade: dict[str, Any], price: float) -> str | None:
        side = trade.get("side")
        tp = trade.get("tp_price")
        sl = trade.get("sl_price")
        if side == "UP":
            if tp and price >= float(tp):
                return "take_profit"
            if sl and price <= float(sl):
                return "stop_loss"
        elif side == "DOWN":
            if tp and price <= float(tp):
                return "take_profit"
            if sl and price >= float(sl):
                return "stop_loss"
        return None


class EngineRegistry:
    def __init__(self) -> None:
        settings = get_settings()
        raw = settings.load_yaml("engines.yaml") or {}
        catalog: dict[str, TradingEngine] = {}
        for key, spec in (raw.get("engines") or {}).items():
            catalog[key] = TradingEngine(
                EngineSpec(
                    key=key,
                    name=spec.get("name", key),
                    description=spec.get("description", ""),
                    tp_pct=float(spec.get("tp_pct", 0.01)),
                    sl_pct=float(spec.get("sl_pct", 0.008)),
                    enter_threshold=float(spec.get("enter_threshold", 0.05)),
                    weights=spec.get("weights") or {},
                )
            )
        self.catalog = catalog
        self.default_active = list(raw.get("active") or list(catalog.keys())[:3])

    def all_meta(self) -> list[dict[str, Any]]:
        return [
            {
                "key": eng.key,
                "name": eng.name,
                "description": eng.spec.description,
                "tp_pct": eng.spec.tp_pct,
                "sl_pct": eng.spec.sl_pct,
            }
            for eng in self.catalog.values()
        ]

    def get(self, key: str) -> TradingEngine:
        if key not in self.catalog:
            raise KeyError(key)
        return self.catalog[key]

    def active_keys(self) -> list[str]:
        with get_engine().begin() as conn:
            row = conn.execute(
                text("SELECT value FROM system_configuration WHERE key = 'active_engines'")
            ).scalar()
        if not row:
            return list(self.default_active)
        if isinstance(row, dict):
            keys = row.get("keys") or []
        else:
            import json

            keys = (json.loads(row) or {}).get("keys") or []
        return [k for k in keys if k in self.catalog] or list(self.default_active)

    def set_active(self, keys: list[str]) -> list[str]:
        valid = [k for k in keys if k in self.catalog]
        if not valid:
            valid = list(self.default_active)
        import json

        with get_engine().begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO system_configuration (key, value)
                    VALUES ('active_engines', CAST(:value AS jsonb))
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
                    """
                ),
                {"value": json.dumps({"keys": valid})},
            )
        return valid

    def active(self) -> list[TradingEngine]:
        return [self.catalog[k] for k in self.active_keys()]
