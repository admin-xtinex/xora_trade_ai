from __future__ import annotations

import json
from typing import Any

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
    if name == "rsi":
        return f"RSI was {feats.get('rsi')}; that mapped to {decision}."
    if name == "macd":
        return f"MACD histogram {feats.get('histogram')} pointed {decision}."
    if name == "trend":
        return f"EMA trend_up={feats.get('trend_up')} so bias was {decision}."
    if name == "bollinger":
        return f"Bollinger position {feats.get('position')} suggested {decision}."
    if name == "volume":
        return f"Volume ratio {feats.get('volume_ratio')} confirmed {decision}."
    if name == "momentum":
        return f"10-bar ROC {feats.get('roc_10')} pointed {decision}."
    if name == "atr":
        return f"ATR% {feats.get('atr_pct')} was volatility context."
    if name == "volatility":
        return f"Realized vol {feats.get('realized_vol_20')} was context."
    return f"{name} voted {decision}."


def build_trade_analysis(trade: dict[str, Any]) -> dict[str, Any]:
    modules = trade.get("modules") or []
    supporting = []
    opposing = []
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
    pnl = trade.get("pnl_usdt")
    reason = trade.get("exit_reason")
    if reason == "take_profit":
        outcome = "Take profit hit. Price reached the planned TP."
        wrong = None
    elif reason == "stop_loss":
        outcome = "Stop loss hit. Price moved against the entry."
        wrong = (
            f"Entered {side} at {trade.get('entry_price')} but price went to {trade.get('exit_price')}. "
            + ("Supporting modules: " + ", ".join(r["module"] for r in supporting) if supporting else "Weak module agreement.")
        )
    elif reason == "session_end":
        outcome = "15-minute session ended so the demo trade was closed at live Binance price."
        wrong = None if (pnl or 0) >= 0 else "Session clock expired while the move had not reached TP."
    elif trade.get("status") == "open":
        outcome = "Trade is still open. TP/SL have not printed yet."
        wrong = None
    else:
        outcome = f"Closed ({reason})."
        wrong = None if (pnl or 0) >= 0 else "Exit was against the predicted side."
    return {
        "id": trade.get("id"),
        "symbol": trade.get("coin_symbol") or trade.get("symbol"),
        "side": side,
        "status": trade.get("status"),
        "bucket": trade.get("bucket") or trade.get("source"),
        "margin_usdt": trade.get("margin_usdt"),
        "leverage": trade.get("leverage"),
        "entry_price": trade.get("entry_price"),
        "exit_price": trade.get("exit_price"),
        "tp_price": trade.get("tp_price"),
        "sl_price": trade.get("sl_price"),
        "pnl_usdt": pnl,
        "pnl_pct": trade.get("pnl_pct"),
        "opened_at": trade.get("opened_at"),
        "closed_at": trade.get("closed_at"),
        "why_entered": trade.get("entry_reason"),
        "why_exited": reason,
        "outcome": outcome,
        "what_went_wrong": wrong,
        "analysis_data": trade.get("analysis"),
        "supporting_modules": supporting,
        "opposing_modules": opposing,
        "confidence": trade.get("confidence"),
        "score": trade.get("score"),
        "engine_version": trade.get("engine_version"),
        "strategy_name": trade.get("strategy_name"),
    }


def build_analysis(detail: dict[str, Any], validation: dict[str, Any] | None = None) -> dict[str, Any]:
    analytics = Analytics()
    trades = analytics.trades()
    for trade in trades:
        if str(trade.get("prediction_id")) == str(detail.get("id")):
            full = analytics.trade_detail(trade["id"]) or trade
            return build_trade_analysis(full)
    return {"symbol": detail.get("symbol"), "why_entered": "No paper trade attached yet."}


def attach_validation(store: Store, prediction_id: str) -> dict | None:
    rows = store.list_rows("validations", limit=200)
    for row in rows:
        if str(row.get("prediction_id")) == str(prediction_id):
            return row
    return None
