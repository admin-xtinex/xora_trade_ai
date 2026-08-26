from __future__ import annotations

import json
from typing import Any

from xora.application.pnl import compute_pnl
from xora.persistence.queries import Analytics
from xora.persistence.store import Store


def _features(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _module_why(name: str | None, feats: dict, decision: str | None) -> str:
    name = name or "module"
    mapping = {
        "rsi": f"RSI was {feats.get('rsi')}; mapped to {decision}.",
        "macd": f"MACD histogram {feats.get('histogram')} pointed {decision}.",
        "trend": f"EMA trend_up={feats.get('trend_up')} so bias was {decision}.",
        "bollinger": f"Bollinger position {feats.get('position')} suggested {decision}.",
        "volume": f"Volume ratio {feats.get('volume_ratio')} supported {decision}.",
        "momentum": f"10-bar ROC {feats.get('roc_10')} pointed {decision}.",
        "atr": f"ATR% {feats.get('atr_pct')} set volatility context.",
        "volatility": f"Realized vol {feats.get('realized_vol_20')} was context.",
    }
    return mapping.get(name, f"{name} voted {decision}.")


def _decision_points(trade: dict[str, Any], analysis: dict[str, Any], modules: list[dict]) -> list[str]:
    points: list[str] = []
    side = trade.get("side") or analysis.get("side") or "—"
    engine = trade.get("engine_name") or analysis.get("engine_name") or analysis.get("engine") or "engine"
    entry = trade.get("entry_price")
    tp = trade.get("tp_price")
    sl = trade.get("sl_price")
    score = analysis.get("score")
    points.append(f"1. Engine {engine} chose {side} at live Binance mark {entry}.")
    points.append(f"2. Take-profit set at {tp}; stop-loss set at {sl}.")
    points.append(
        f"3. Position size: margin {trade.get('margin_usdt') or 10} USDT × {trade.get('leverage') or 15}x "
        f"→ qty {trade.get('qty')}."
    )
    if score is not None:
        points.append(f"4. Decision score was {float(score):.4f} (positive = UP bias, negative = DOWN bias).")
    else:
        points.append("4. Decision used available live price + 24h change when full module score was unavailable.")
    if analysis.get("forced"):
        points.append("5. Score was inside neutral band, so direction was forced from residual bias / 24h change.")
    elif analysis.get("fallback"):
        points.append("5. Fallback entry: full candle analysis failed, used ticker + bucket change only.")
    else:
        points.append("5. Score cleared the engine enter threshold, so the side was taken without force.")

    ranked = sorted(modules, key=lambda m: abs(float(m.get("contribution") or 0)), reverse=True)
    for i, m in enumerate(ranked[:4], start=6):
        feats = _features(m.get("raw_features"))
        points.append(
            f"{i}. Module {m.get('module_name')} voted {m.get('decision')} "
            f"(contribution {float(m.get('contribution') or 0):+.3f}). {_module_why(m.get('module_name'), feats, m.get('decision'))}"
        )

    mods = analysis.get("modules") or []
    if isinstance(mods, list):
        for i, item in enumerate(mods[:4], start=len(points) + 1):
            points.append(f"{i}. Signal stack: {item}")

    while len(points) < 5:
        points.append(f"{len(points) + 1}. Paper trade only — no exchange order was sent.")
    return points[:12]


def build_trade_analysis(trade: dict[str, Any]) -> dict[str, Any]:
    modules = trade.get("modules") or []
    supporting, opposing = [], []
    side = trade.get("side")
    for m in modules:
        feats = _features(m.get("raw_features"))
        row = {
            "module": m.get("module_name"),
            "decision": m.get("decision"),
            "contribution": m.get("contribution"),
            "why": _module_why(m.get("module_name"), feats, m.get("decision")),
            "features": feats,
        }
        if m.get("decision") == side:
            supporting.append(row)
        elif m.get("decision") in {"UP", "DOWN"}:
            opposing.append(row)
    analysis = trade.get("analysis") or {}
    if isinstance(analysis, str):
        try:
            analysis = json.loads(analysis)
        except json.JSONDecodeError:
            analysis = {}
    if not isinstance(analysis, dict):
        analysis = {}

    stored_points = analysis.get("decision_points")
    if isinstance(stored_points, list) and len(stored_points) >= 5:
        decision_points = [str(p) for p in stored_points]
    else:
        decision_points = _decision_points(trade, analysis, modules)

    proof = analysis.get("pnl_proof")
    if not proof and trade.get("exit_price") is not None:
        proof = compute_pnl(
            side or "UP",
            float(trade.get("entry_price") or 0),
            float(trade.get("exit_price") or 0),
            float(trade.get("qty") or 0),
            float(trade.get("margin_usdt") or 10),
            int(trade.get("leverage") or 15),
        )
    reason = trade.get("exit_reason")
    pnl = trade.get("pnl_usdt")
    if reason == "take_profit":
        outcome, wrong = "Take profit hit on live Binance price.", None
    elif reason == "stop_loss":
        outcome = "Stop loss hit on live Binance price."
        wrong = f"Entered {side} at {trade.get('entry_price')} and live price printed {trade.get('exit_price')}."
    elif reason == "session_end":
        outcome = "15-minute IST slot ended. Closed at live Binance price."
        wrong = None if (pnl or 0) >= 0 else "Slot ended before TP."
    elif trade.get("status") == "open":
        outcome, wrong = "Still open. Watching live 15m candle + ticker.", None
    else:
        outcome, wrong = f"Closed ({reason}).", None

    return {
        "id": trade.get("id"),
        "symbol": trade.get("coin_symbol") or trade.get("symbol"),
        "engine_name": trade.get("engine_name") or analysis.get("engine") or analysis.get("engine_name"),
        "side": side,
        "status": trade.get("status"),
        "entry_price": trade.get("entry_price"),
        "exit_price": trade.get("exit_price"),
        "tp_price": trade.get("tp_price"),
        "sl_price": trade.get("sl_price"),
        "qty": trade.get("qty"),
        "margin_usdt": trade.get("margin_usdt"),
        "leverage": trade.get("leverage"),
        "pnl_usdt": pnl,
        "opened_at": trade.get("opened_at"),
        "closed_at": trade.get("closed_at"),
        "why_entered": trade.get("entry_reason") or analysis.get("entry_reason") or "—",
        "why_exited": reason,
        "outcome": outcome,
        "what_went_wrong": wrong,
        "decision_points": decision_points,
        "pnl_proof": proof,
        "analysis_data": analysis,
        "supporting_modules": supporting,
        "opposing_modules": opposing,
        "modules": [
            {
                "module": m.get("module_name"),
                "decision": m.get("decision"),
                "contribution": m.get("contribution"),
                "why": _module_why(m.get("module_name"), _features(m.get("raw_features")), m.get("decision")),
            }
            for m in modules
        ],
    }


def build_analysis(detail: dict[str, Any], validation: dict[str, Any] | None = None) -> dict[str, Any]:
    analytics = Analytics()
    for trade in analytics.trades():
        if str(trade.get("prediction_id")) == str(detail.get("id")):
            return build_trade_analysis(analytics.trade_detail(trade["id"]) or trade)
    return {"symbol": detail.get("symbol"), "why_entered": "No paper trade attached yet.", "decision_points": []}


def attach_validation(store: Store, prediction_id: str) -> dict | None:
    for row in store.list_rows("validations", limit=200):
        if str(row.get("prediction_id")) == str(prediction_id):
            return row
    return None
