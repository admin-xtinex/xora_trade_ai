from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text

from xora.application.clock import next_full_slot, now_ist, slot_label
from xora.application.pnl import compute_pnl
from xora.persistence.db import get_engine
from xora.persistence.store import _serialize_row


class Analytics:
    def __init__(self) -> None:
        self.engine = get_engine()

    def coin_stats(self, min_hit_rate: float | None = None, min_samples: int = 0) -> list[dict[str, Any]]:
        sql = """
            SELECT c.id AS coin_id, c.symbol,
                   COUNT(pt.id)::int AS sample_size,
                   COUNT(*) FILTER (WHERE pt.status = 'closed' AND pt.pnl_usdt > 0)::int AS wins,
                   COUNT(*) FILTER (WHERE pt.status = 'closed' AND pt.pnl_usdt <= 0)::int AS losses,
                   COUNT(*) FILTER (WHERE pt.status = 'closed')::int AS closed_trades,
                   AVG(CASE WHEN pt.status = 'closed' AND pt.pnl_usdt > 0 THEN 1.0
                            WHEN pt.status = 'closed' THEN 0.0
                            ELSE NULL END) AS hit_rate,
                   AVG(CASE WHEN pt.status = 'closed' THEN pt.pnl_usdt ELSE NULL END) AS avg_pnl,
                   SUM(CASE WHEN pt.status = 'closed' THEN pt.pnl_usdt ELSE 0 END) AS net_pnl,
                   SUM(CASE WHEN pt.status = 'open' THEN 1 ELSE 0 END)::int AS open_trades
            FROM coins c
            LEFT JOIN paper_trades pt ON pt.coin_id = c.id
            GROUP BY c.id, c.symbol
            HAVING COUNT(pt.id) >= :min_samples
            ORDER BY hit_rate DESC NULLS LAST, c.symbol
        """
        with self.engine.begin() as conn:
            rows = [_serialize_row(dict(r)) for r in conn.execute(text(sql), {"min_samples": min_samples}).mappings().all()]
        if min_hit_rate is None:
            return rows
        return [r for r in rows if (r.get("hit_rate") or 0) >= min_hit_rate]

    def trades(self, status: str | None = None, engine: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        sql = "SELECT pt.*, c.symbol AS coin_symbol FROM paper_trades pt JOIN coins c ON c.id = pt.coin_id WHERE 1=1"
        params: dict[str, Any] = {"limit": limit}
        if status:
            sql += " AND pt.status = :status"
            params["status"] = status
        if engine:
            sql += " AND pt.engine_name = :engine"
            params["engine"] = engine
        sql += " ORDER BY pt.opened_at DESC LIMIT :limit"
        with self.engine.begin() as conn:
            return [_serialize_row(dict(r)) for r in conn.execute(text(sql), params).mappings().all()]

    def trade_detail(self, trade_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT pt.*, c.symbol AS coin_symbol, p.confidence, p.score, p.market_regime,
                           p.engine_version, p.strategy_name, p.feature_version, p.config_version
                    FROM paper_trades pt
                    JOIN coins c ON c.id = pt.coin_id
                    LEFT JOIN predictions p ON p.id = pt.prediction_id
                    WHERE pt.id = CAST(:id AS uuid)
                    """
                ),
                {"id": trade_id},
            ).mappings().first()
            if not row:
                return None
            item = _serialize_row(dict(row))
            if item.get("prediction_id"):
                mods = conn.execute(
                    text("SELECT * FROM prediction_modules WHERE prediction_id = CAST(:id AS uuid)"),
                    {"id": item["prediction_id"]},
                ).mappings().all()
                item["modules"] = [_serialize_row(dict(m)) for m in mods]
            else:
                item["modules"] = []
            return item

    def current_session(self) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT * FROM trade_sessions ORDER BY started_at DESC LIMIT 1")).mappings().first()
            return _serialize_row(dict(row)) if row else None

    def start_session_window(self, start, end, universe: list[dict]) -> dict[str, Any]:
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE trade_sessions SET status = 'closed' WHERE status IN ('warmup','waiting','live')"))
            row = conn.execute(
                text(
                    """
                    INSERT INTO trade_sessions (status, started_at, warmup_until, ends_at, universe, notes)
                    VALUES ('waiting', :started, :live_from, :ends, CAST(:universe AS jsonb), :notes)
                    RETURNING *
                    """
                ),
                {
                    "started": datetime.now(timezone.utc),
                    "live_from": start,
                    "ends": end,
                    "universe": json.dumps(universe),
                    "notes": slot_label(start, end),
                },
            ).mappings().one()
            return _serialize_row(dict(row))

    def mark_session_live(self, session_id: UUID) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE trade_sessions SET status = 'live' WHERE id = :id"), {"id": session_id})

    def close_session(self, session_id: UUID) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("UPDATE trade_sessions SET status = 'closed' WHERE id = :id"), {"id": session_id})

    def save_universe(self, picks: list[dict[str, Any]]) -> None:
        with self.engine.begin() as conn:
            for pick in picks:
                conn.execute(
                    text(
                        """
                        INSERT INTO universe_picks (symbol, source, change_pct, quote_volume, last_price)
                        VALUES (:symbol, :source, :change_pct, :quote_volume, :last_price)
                        """
                    ),
                    pick,
                )

    def open_pairs(self) -> set[tuple[str, str]]:
        with self.engine.begin() as conn:
            rows = conn.execute(text("SELECT symbol, COALESCE(engine_name, '') FROM paper_trades WHERE status = 'open'")).all()
            return {(r[0], r[1]) for r in rows}

    def session_trade_count(self, session_id: UUID) -> int:
        with self.engine.begin() as conn:
            n = conn.execute(text("SELECT COUNT(*) FROM paper_trades WHERE session_id = :sid"), {"sid": session_id}).scalar_one()
            return int(n or 0)

    def open_trades(self) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            return [dict(r) for r in conn.execute(text("SELECT * FROM paper_trades WHERE status = 'open'")).mappings().all()]

    def open_paper(self, payload: dict[str, Any]) -> UUID:
        cols = [
            "coin_id", "prediction_id", "symbol", "side", "source", "margin_usdt", "leverage",
            "notional_usdt", "entry_price", "qty", "status", "hold_minutes", "tp_price", "sl_price",
            "entry_reason", "analysis", "session_id", "bucket", "engine_name",
        ]
        payload = {**payload, "status": payload.get("status", "open")}
        if isinstance(payload.get("analysis"), dict):
            payload["analysis"] = json.dumps(payload["analysis"])
        fields = ", ".join(cols)
        values = ", ".join(f":{c}" if c != "analysis" else "CAST(:analysis AS jsonb)" for c in cols)
        with self.engine.begin() as conn:
            row = conn.execute(text(f"INSERT INTO paper_trades ({fields}) VALUES ({values}) RETURNING id"), {c: payload.get(c) for c in cols}).one()
            return row.id

    def close_trade(self, trade_id: UUID, exit_price: float, reason: str) -> None:
        with self.engine.begin() as conn:
            open_row = conn.execute(
                text("SELECT * FROM paper_trades WHERE id = :id AND status = 'open'"),
                {"id": trade_id},
            ).mappings().first()
            if not open_row:
                return
            proof = compute_pnl(
                open_row["side"],
                float(open_row["entry_price"]),
                float(exit_price),
                float(open_row["qty"]),
                float(open_row["margin_usdt"] or 10),
                int(open_row["leverage"] or 15),
            )
            analysis = open_row.get("analysis") or {}
            if isinstance(analysis, str):
                analysis = json.loads(analysis)
            analysis["exit_reason"] = reason
            analysis["pnl_proof"] = proof
            conn.execute(
                text(
                    """
                    UPDATE paper_trades
                    SET exit_price = :exit_price, pnl_usdt = :pnl, pnl_pct = :pnl_pct,
                        is_full_loss = :full_loss, status = 'closed', closed_at = now(),
                        exit_reason = :reason, analysis = CAST(:analysis AS jsonb)
                    WHERE id = :id
                    """
                ),
                {
                    "exit_price": exit_price,
                    "pnl": proof["pnl_usdt"],
                    "pnl_pct": proof["pnl_pct_notional"],
                    "full_loss": proof["pnl_usdt"] <= -0.9 * proof["margin_usdt"],
                    "reason": reason,
                    "analysis": json.dumps(analysis),
                    "id": trade_id,
                },
            )

    def live_snapshot(self) -> dict[str, Any]:
        start, end = next_full_slot()
        with self.engine.begin() as conn:
            open_t = conn.execute(text("SELECT COUNT(*) FROM paper_trades WHERE status='open'")).scalar_one()
            closed = conn.execute(text("SELECT COUNT(*) FROM paper_trades WHERE status='closed'")).scalar_one()
            pnl = conn.execute(text("SELECT COALESCE(SUM(pnl_usdt),0) FROM paper_trades WHERE status='closed'")).scalar_one()
            session = conn.execute(text("SELECT * FROM trade_sessions ORDER BY started_at DESC LIMIT 1")).mappings().first()
        return {
            "open_trades": int(open_t or 0),
            "closed_trades": int(closed or 0),
            "net_pnl": float(pnl or 0),
            "session": _serialize_row(dict(session)) if session else None,
            "clock": {
                "timezone": "Asia/Kolkata",
                "now": now_ist().isoformat(),
                "next_slot": slot_label(start, end),
                "next_start": start.isoformat(),
                "next_end": end.isoformat(),
            },
        }
