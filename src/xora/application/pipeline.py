from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from xora import __version__
from xora.application.clock import next_full_slot, now_ist, slot_label
from xora.application.pnl import compute_pnl
from xora.config.settings import get_settings
from xora.domain.enums import Direction
from xora.engines.registry import EngineRegistry, TradingEngine
from xora.market.providers.binance import BinanceMarketProvider
from xora.market.universe import BinanceUniverseBuilder, UniversePick
from xora.modules.registry import ModuleRegistry
from xora.persistence.queries import Analytics
from xora.persistence.store import Store

logger = logging.getLogger("xora")


def _hash_payload(symbol: str, timeframe: str, last_time: int) -> str:
    return hashlib.sha256(f"{symbol}:{timeframe}:{last_time}".encode()).hexdigest()


class PredictionPlatform:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.store = Store()
        self.analytics = Analytics()
        self.registry = ModuleRegistry(self.store)
        self.engines = EngineRegistry()
        self.provider = BinanceMarketProvider()
        self.universe_builder = BinanceUniverseBuilder()
        self._picks: list[UniversePick] = []

    def start_trading(self) -> dict[str, Any]:
        current = self.analytics.current_session()
        if current and current.get("status") in {"waiting", "live"}:
            return {"ok": True, "session": current, "note": "session already armed", "slot": current.get("notes")}
        logger.info("building 50-coin universe from Binance")
        picks = self.universe_builder.build()
        self._picks = picks
        payload = [
            {
                "symbol": p.symbol,
                "bucket": p.bucket,
                "source": p.bucket,
                "change_pct": p.change_pct,
                "quote_volume": p.quote_volume,
                "last_price": p.last_price,
            }
            for p in picks
        ]
        self.analytics.save_universe(payload)
        start, end = next_full_slot()
        session = self.analytics.start_session_window(start, end, payload)
        logger.info("armed slot %s universe=%s", slot_label(start, end), len(picks))
        return {"ok": True, "session": session, "slot": slot_label(start, end), "now": now_ist().isoformat()}

    def run_cycle(self) -> dict[str, Any]:
        session = self.analytics.current_session()
        if not session or session.get("status") not in {"waiting", "live", "warmup"}:
            armed = self.start_trading()
            session = armed["session"]
            self.store.heartbeat()
            return {
                "phase": "waiting",
                "detail": "auto-armed next IST slot",
                "slot": armed.get("slot"),
                "starts_at": session.get("warmup_until"),
                "ends_at": session.get("ends_at"),
                "universe": len(self._picks),
            }
        self._load_picks(session)
        now = datetime.now(timezone.utc)
        live_from = _ts(session.get("warmup_until") or session.get("started_at"))
        ends_at = _ts(session["ends_at"])
        active = [e.key for e in self.engines.active()]
        if now < live_from:
            self.store.heartbeat()
            return {
                "phase": "waiting",
                "slot": session.get("notes"),
                "starts_at": session.get("warmup_until"),
                "ends_at": session.get("ends_at"),
                "engines": active,
                "universe": len(self._picks),
                "detail": f"waiting until {session.get('warmup_until')}",
            }
        if session.get("status") in {"waiting", "warmup"}:
            self.analytics.mark_session_live(session["id"])
            session["status"] = "live"
            logger.info("slot live engines=%s coins=%s", active, len(self._picks))
        closed = self._manage_exits()
        if now >= ends_at:
            closed += self._close_all("session_end")
            self.analytics.close_session(session["id"])
            self.store.heartbeat()
            return {"phase": "session_closed", "closed": closed, "engines": active, "slot": session.get("notes")}
        opened, errors = self._trade_universe(session)
        if errors:
            logger.warning("trade errors %s", errors[:10])
        self.store.heartbeat()
        return {
            "phase": "live",
            "opened": opened,
            "closed": closed,
            "errors": errors,
            "engines": active,
            "universe": len(self._picks),
            "slot": session.get("notes"),
            "mark": "binance_live_15m",
        }

    def _load_picks(self, session: dict[str, Any]) -> None:
        raw = session.get("universe") or []
        if isinstance(raw, str):
            raw = json.loads(raw)
        self._picks = [
            UniversePick(
                symbol=p["symbol"],
                bucket=p.get("bucket") or p.get("source") or "ai",
                change_pct=float(p.get("change_pct") or 0),
                quote_volume=float(p.get("quote_volume") or 0),
                last_price=float(p.get("last_price") or 0),
            )
            for p in raw
        ]

    def _trade_universe(self, session: dict[str, Any]) -> tuple[int, list[str]]:
        opened = 0
        errors: list[str] = []
        active = self.engines.active()
        if not active:
            return 0, ["no engine selected"]
        already = self.analytics.open_pairs()
        for pick in self._picks:
            needed = [eng for eng in active if (pick.symbol, eng.key) not in already]
            if not needed:
                continue
            try:
                snapshot, results, coin_id, snapshot_id, feature_set_id = self._analyze(pick)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{pick.symbol}: {exc}")
                continue
            for eng in needed:
                try:
                    self._open_with_engine(pick, session, eng, snapshot, results, coin_id, snapshot_id, feature_set_id)
                    already.add((pick.symbol, eng.key))
                    opened += 1
                    logger.info("opened %s %s %s", eng.key, pick.symbol, session.get("notes"))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{pick.symbol}/{eng.key}: {exc}")
        return opened, errors

    def _analyze(self, pick: UniversePick):
        snapshot = self.provider.fetch_ohlcv(pick.symbol, "15m", limit=120)
        live = self.provider.fetch_last_price(pick.symbol)
        if snapshot.candles:
            snapshot.candles[-1].close = live
        snapshot.ticker = {"last": live, "interval": "15m", "forming": True}
        coin_id = self.store.upsert_coin(pick.symbol, snapshot.venue)
        snapshot.coin_id = coin_id
        last_time = snapshot.candles[-1].time if snapshot.candles else 0
        snapshot_id = self.store.insert_snapshot(
            coin_id, snapshot, _hash_payload(pick.symbol, snapshot.timeframe, last_time)
        )
        results = self.registry.extract(snapshot)
        feature_set_id = self.store.insert_feature_set(
            coin_id, snapshot_id, self.registry.feature_version(), self.registry.config_version(), results
        )
        return snapshot, results, coin_id, snapshot_id, feature_set_id

    def _open_with_engine(
        self, pick, session, eng: TradingEngine, snapshot, results, coin_id, snapshot_id, feature_set_id
    ) -> None:
        decision = eng.decide(results, fallback_change=pick.change_pct)
        now = datetime.now(timezone.utc)
        prediction_id = self.store.insert_prediction(
            {
                "coin_id": coin_id,
                "feature_set_id": feature_set_id,
                "snapshot_id": snapshot_id,
                "direction": decision.direction.value,
                "horizon": "15m",
                "magnitude": decision.magnitude,
                "confidence": decision.confidence,
                "score": decision.score,
                "market_regime": decision.market_regime,
                "engine_version": __version__,
                "strategy_name": eng.key,
                "model_name": eng.name,
                "feature_version": self.registry.feature_version(),
                "config_version": self.registry.config_version(),
                "experiment_name": "production",
                "predicted_at": now,
                "horizon_at": now + timedelta(minutes=15),
                "metadata": json.dumps(decision.metadata),
            },
            [
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
            ],
        )
        entry = float((snapshot.ticker or {}).get("last") or snapshot.last_price or pick.last_price)
        tp, sl = eng.levels(decision.direction.value, entry)
        margin = self.settings.paper_margin_usdt
        lev = self.settings.paper_leverage
        notional = margin * lev
        qty = notional / entry if entry else 0
        reasons = [
            f"{c.module_name}={c.decision}"
            for c in sorted(decision.contributions, key=lambda x: abs(x.contribution), reverse=True)[:4]
        ]
        self.analytics.open_paper(
            {
                "coin_id": coin_id,
                "prediction_id": prediction_id,
                "symbol": pick.symbol,
                "side": decision.direction.value,
                "source": pick.bucket,
                "margin_usdt": margin,
                "leverage": lev,
                "notional_usdt": notional,
                "entry_price": entry,
                "qty": qty,
                "hold_minutes": 15,
                "tp_price": tp,
                "sl_price": sl,
                "entry_reason": f"{eng.name} entered {decision.direction.value} on live 15m mark {entry}. score={decision.score:.3f}. " + "; ".join(reasons),
                "analysis": {
                    "engine": eng.key,
                    "engine_name": eng.name,
                    "mark": "binance_live_ticker_on_15m_candle",
                    "slot": session.get("notes"),
                    "score": decision.score,
                    "modules": reasons,
                },
                "session_id": session["id"],
                "bucket": pick.bucket,
                "engine_name": eng.key,
            }
        )

    def _manage_exits(self) -> int:
        closed = 0
        catalog = self.engines.catalog
        for trade in self.analytics.open_trades():
            try:
                price = self.provider.fetch_last_price(trade["symbol"])
            except Exception:  # noqa: BLE001
                continue
            eng = catalog.get(trade.get("engine_name") or "smart_ai") or catalog.get("smart_ai")
            reason = eng.should_exit(trade, price) if eng else None
            if reason:
                self.analytics.close_trade(trade["id"], price, reason)
                self._validate_trade(trade, price, reason)
                closed += 1
        return closed

    def _close_all(self, reason: str) -> int:
        closed = 0
        for trade in self.analytics.open_trades():
            try:
                price = self.provider.fetch_last_price(trade["symbol"])
            except Exception:  # noqa: BLE001
                price = float(trade["entry_price"])
            self.analytics.close_trade(trade["id"], price, reason)
            self._validate_trade(trade, price, reason)
            closed += 1
        return closed

    def _validate_trade(self, trade: dict[str, Any], exit_price: float, reason: str) -> None:
        if not trade.get("prediction_id"):
            return
        entry = float(trade["entry_price"])
        change = (exit_price - entry) / entry if entry else 0.0
        predicted = trade["side"]
        if change > 0.0005:
            actual = Direction.UP.value
        elif change < -0.0005:
            actual = Direction.DOWN.value
        else:
            actual = Direction.NEUTRAL.value
        proof = compute_pnl(predicted, entry, exit_price, float(trade.get("qty") or 0), float(trade.get("margin_usdt") or 10), int(trade.get("leverage") or 15))
        self.store.insert_validation(
            {
                "prediction_id": trade["prediction_id"],
                "predicted_direction": predicted,
                "actual_direction": actual,
                "predicted_magnitude": None,
                "actual_magnitude": change,
                "magnitude_error": None,
                "confidence": 0.0,
                "calibration_bucket": "mid",
                "market_regime": None,
                "is_correct": proof["pnl_usdt"] > 0 or reason == "take_profit",
                "reference_price": entry,
                "realized_price": exit_price,
                "extras": json.dumps({"reason": reason, "engine": trade.get("engine_name"), "pnl_proof": proof}),
            }
        )


def _ts(value):
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value
