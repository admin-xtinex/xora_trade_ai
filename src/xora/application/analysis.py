from __future__ import annotations

import json
from typing import Any

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


def build_analysis(detail: dict[str, Any], validation: dict[str, Any] | None = None) -> dict[str, Any]:
    modules = detail.get("modules") or []
    direction = detail.get("direction")
    supporting = [m for m in modules if m.get("decision") == direction]
    opposing = [m for m in modules if m.get("decision") and m.get("decision") not in {direction, "NEUTRAL", "NONE"}]
    reasons = []
    for m in sorted(supporting, key=lambda x: abs(float(x.get("contribution") or 0)), reverse=True):
        feats = _features(m.get("raw_features"))
        reasons.append(
            {
                "module": m.get("module_name"),
                "decision": m.get("decision"),
                "weight": m.get("weight"),
                "contribution": m.get("contribution"),
                "features": feats,
                "why": _module_why(m.get("module_name"), feats, m.get("decision")),
            }
        )
    entry_basis = (
        f"5m setup entered {direction} because weighted modules scored {float(detail.get('score') or 0):.3f} "
        f"with confidence {float(detail.get('confidence') or 0):.0%}. "
        f"Top votes: " + ", ".join(f"{r['module']} ({r['decision']})" for r in reasons[:4] or [{"module": "none", "decision": "n/a"}])
    )
    exit_basis = "Exit is forced at the 5-minute horizon. This platform does not hold beyond one 5m candle."
    outcome = None
    mistake = None
    if validation:
        actual = validation.get("actual_direction")
        change = validation.get("actual_magnitude")
        won = validation.get("is_correct")
        if won:
            outcome = (
                f"Profit path: predicted {direction}, market moved {actual} "
                f"({float(change or 0):.2%} from entry reference). The 5m exit captured that move."
            )
        else:
            outcome = (
                f"Loss path: predicted {direction}, market actually {actual} "
                f"({float(change or 0):.2%}). 5m exit closed against the call."
            )
            wrong = ", ".join(m.get("module_name") for m in supporting) or "the composite score"
            mistake = (
                f"The call was wrong because {wrong} dominated the score, but price did not follow. "
                + (f"Opposing modules were {', '.join(m.get('module_name') for m in opposing)}." if opposing else "No strong opposing module voted the other way.")
            )
    return {
        "symbol": detail.get("symbol"),
        "timeframe": "5m",
        "hold": "5 minutes only",
        "direction": direction,
        "confidence": detail.get("confidence"),
        "score": detail.get("score"),
        "regime": detail.get("market_regime"),
        "predicted_at": detail.get("predicted_at"),
        "horizon_at": detail.get("horizon_at"),
        "entry_basis": entry_basis,
        "exit_basis": exit_basis,
        "supporting_modules": reasons,
        "opposing_modules": [
            {"module": m.get("module_name"), "decision": m.get("decision"), "contribution": m.get("contribution")}
            for m in opposing
        ],
        "outcome": outcome,
        "why_wrong": mistake,
        "engine": {
            "engine_version": detail.get("engine_version"),
            "strategy_name": detail.get("strategy_name"),
            "feature_version": detail.get("feature_version"),
            "config_version": detail.get("config_version"),
        },
    }


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
        return f"ATR% {feats.get('atr_pct')} used only as size/volatility context."
    if name == "volatility":
        return f"Realized vol {feats.get('realized_vol_20')} was context, not a trigger."
    return f"{name} voted {decision}."


def attach_validation(store: Store, prediction_id: str) -> dict | None:
    rows = store.list_rows("validations", limit=200)
    for row in rows:
        if str(row.get("prediction_id")) == str(prediction_id):
            return row
    return None
