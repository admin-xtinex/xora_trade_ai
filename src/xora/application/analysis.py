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
        "rsi": f"RSI was {feats.get('rsi')}; that mapped to {decision}.",
        "macd": f"MACD histogram {feats.get('histogram')} pointed {decision}.",
        "trend": f"EMA trend_up={feats.get('trend_up')} so bias was {decision}.",
        "bollinger": f"Bollinger position {feats.get('position')} suggested {decision}.",
        "volume": f"Volume ratio {feats.get('volume_ratio')} confirmed {decision}.",
        "momentum": f"10-bar ROC {feats.get('roc_10')} pointed {decision}.",
        "atr": f"ATR% {feats.get('atr_pct')} was volatility context.",
        "volatility": f"Realized vol {feats.get('realized_vol_20')} was context.",
    }
    return mapping.get(name, f"{name} voted {decision}.")


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
        analysis = json.loads(analysis)
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
        "engine_name": trade.get("engine_name"),
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
        "why_entered": trade.get("entry_reason"),
        "why_exited": reason,
        "outcome": outcome,
        "what_went_wrong": wrong,
        "pnl_proof": proof,
        "analysis_data": analysis,
        "supporting_modules": supporting,
        "opposing_modules": opposing,
    }


def build_analysis(detail: dict[str, Any], validation: dict[str, Any] | None = None) -> dict[str, Any]:
    analytics = Analytics()
    for trade in analytics.trades():
        if str(trade.get("prediction_id")) == str(detail.get("id")):
            return build_trade_analysis(analytics.trade_detail(trade["id"]) or trade)
    return {"symbol": detail.get("symbol"), "why_entered": "No paper trade attached yet."}


def attach_validation(store: Store, prediction_id: str) -> dict | None:
    for row in store.list_rows("validations", limit=200):
        if str(row.get("prediction_id")) == str(prediction_id):
            return row
    return None
