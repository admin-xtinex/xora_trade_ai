from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from xora import __version__
from xora.config.settings import get_settings
from xora.decision.engine import DecisionEngine
from xora.domain.enums import Direction
from xora.market.providers.binance import BinanceMarketProvider
from xora.market.selectors import ConfiguredUniverseSelector
from xora.modules.registry import ModuleRegistry
from xora.persistence.store import Store

logger = logging.getLogger("xora")

HORIZON_DELTA = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
}


def _hash_payload(symbol: str, timeframe: str, last_time: int) -> str:
    raw = f"{symbol}:{timeframe}:{last_time}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _ref_price(ohlcv: Any) -> float | None:
    if isinstance(ohlcv, str):
        ohlcv = json.loads(ohlcv)
    if not ohlcv:
        return None
    return float(ohlcv[-1]["close"])


class PredictionPlatform:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.store = Store()
        self.registry = ModuleRegistry(self.store)
        self.engine = DecisionEngine()
        self.provider = BinanceMarketProvider()
        self.selector = ConfiguredUniverseSelector()

    def run_cycle(self) -> dict[str, Any]:
        symbols = self.selector.select()
        created: list[dict[str, Any]] = []
        errors: list[str] = []
        for symbol in symbols:
            try:
                created.append(self._predict_one(symbol))
            except Exception as exc:  # noqa: BLE001
                logger.exception("cycle failed for %s", symbol)
                errors.append(f"{symbol}: {exc}")
        validated = self.validate_due()
        qualified = self.qualify()
        self.store.heartbeat()
        return {
            "predictions": created,
            "validated": validated,
            "qualified": qualified,
            "errors": errors,
        }

    def _predict_one(self, symbol: str) -> dict[str, Any]:
        snapshot = self.provider.fetch_ohlcv(symbol, self.settings.timeframe, limit=120)
        coin_id = self.store.upsert_coin(symbol, snapshot.venue)
        snapshot.coin_id = coin_id
        payload_hash = _hash_payload(symbol, snapshot.timeframe, snapshot.candles[-1].time if snapshot.candles else 0)
        snapshot_id = self.store.insert_snapshot(coin_id, snapshot, payload_hash)
        results = self.registry.extract(snapshot)
        feature_set_id = self.store.insert_feature_set(
            coin_id,
            snapshot_id,
            self.registry.feature_version(),
            self.registry.config_version(),
            results,
        )
        decision = self.engine.decide(results, self.registry.enabled)
        now = datetime.now(timezone.utc)
        horizon = self.settings.horizon
        payload = {
            "coin_id": coin_id,
            "feature_set_id": feature_set_id,
            "snapshot_id": snapshot_id,
            "direction": decision.direction.value,
            "horizon": horizon,
            "magnitude": decision.magnitude,
            "confidence": decision.confidence,
            "score": decision.score,
            "market_regime": decision.market_regime,
            "engine_version": __version__,
            "strategy_name": self.engine.strategy.name,
            "model_name": "none",
            "feature_version": self.registry.feature_version(),
            "config_version": self.registry.config_version(),
            "experiment_name": "production",
            "predicted_at": now,
            "horizon_at": now + HORIZON_DELTA.get(horizon, timedelta(minutes=15)),
            "metadata": json.dumps(decision.metadata),
        }
        contributions = [
            {
                "module_name": c.module_name,
                "module_version": c.module_version,
                "weight": c.weight,
                "confidence": c.confidence,
                "contribution": c.contribution,
                "decision": c.decision,
                "raw_features": json.dumps(c.raw_features),
            }
            for c in decision.contributions
        ]
        prediction_id = self.store.insert_prediction(payload, contributions)
        return {
            "id": str(prediction_id),
            "symbol": symbol,
            "direction": decision.direction.value,
            "confidence": decision.confidence,
            "score": decision.score,
        }

    def validate_due(self) -> int:
        due = self.store.due_predictions()
        count = 0
        flat = float(self.settings.default_config().get("validation", {}).get("flat_threshold_pct", 0.001))
        for row in due:
            try:
                realized = self.provider.fetch_last_price(row["symbol"])
            except Exception:  # noqa: BLE001
                continue
            reference = _ref_price(row["ohlcv"]) or realized
            change = (realized - reference) / reference if reference else 0.0
            if change > flat:
                actual = Direction.UP.value
            elif change < -flat:
                actual = Direction.DOWN.value
            else:
                actual = Direction.NEUTRAL.value
            predicted = row["direction"]
            bucket = "high" if row["confidence"] >= 0.7 else "mid" if row["confidence"] >= 0.4 else "low"
            self.store.insert_validation(
                {
                    "prediction_id": row["id"],
                    "predicted_direction": predicted,
                    "actual_direction": actual,
                    "predicted_magnitude": row["magnitude"],
                    "actual_magnitude": change,
                    "magnitude_error": None if row["magnitude"] is None else abs((row["magnitude"] or 0) - abs(change)),
                    "confidence": row["confidence"],
                    "calibration_bucket": bucket,
                    "market_regime": row["market_regime"],
                    "is_correct": predicted == actual,
                    "reference_price": reference,
                    "realized_price": realized,
                    "extras": json.dumps({"change": change}),
                }
            )
            count += 1
        if count:
            self.store.refresh_rolling_scores("production", self.engine.strategy.name)
        return count

    def qualify(self) -> int:
        gates = self.settings.default_config().get("qualification", {})
        min_samples = int(gates.get("min_samples", 1))
        min_hit = float(gates.get("min_hit_rate", 0.5))
        min_score = float(gates.get("min_score", 0.0))
        rows = self.store.rolling_scores()
        qualified = []
        for row in rows:
            hit = row.get("hit_rate") or 0.0
            samples = row.get("sample_size") or 0
            score = row.get("score") or 0.0
            ok = samples >= min_samples and hit >= min_hit and score >= min_score
            if not ok:
                continue
            qualified.append(
                {
                    "coin_id": row["coin_id"],
                    "experiment_name": row["experiment_name"],
                    "strategy_name": row["strategy_name"],
                    "reason": f"hit_rate={hit:.2f} n={samples}",
                    "score": score,
                    "gates": json.dumps({"min_samples": min_samples, "min_hit_rate": min_hit}),
                }
            )
        self.store.replace_qualified(qualified, "production", self.engine.strategy.name)
        return len(qualified)
