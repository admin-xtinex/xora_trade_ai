from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from xora.persistence.db import get_engine
from xora.persistence.store import _serialize_row


class Analytics:
    def __init__(self) -> None:
        self.engine = get_engine()

    def coin_stats(self, min_hit_rate: float | None = None, min_samples: int = 1) -> list[dict[str, Any]]:
        sql = """
            SELECT c.id AS coin_id, c.symbol,
                   COUNT(v.id)::int AS sample_size,
                   AVG(CASE WHEN v.is_correct THEN 1.0 ELSE 0.0 END) AS hit_rate,
                   AVG(v.confidence) AS avg_confidence,
                   AVG(pt.pnl_usdt) AS avg_pnl
            FROM coins c
            LEFT JOIN predictions p ON p.coin_id = c.id
            LEFT JOIN validations v ON v.prediction_id = p.id
            LEFT JOIN paper_trades pt ON pt.prediction_id = p.id AND pt.status = 'closed'
            GROUP BY c.id, c.symbol
            HAVING COUNT(v.id) >= :min_samples
            ORDER BY hit_rate DESC NULLS LAST, sample_size DESC
        """
        with self.engine.begin() as conn:
            rows = [_serialize_row(dict(r)) for r in conn.execute(text(sql), {"min_samples": min_samples}).mappings().all()]
        if min_hit_rate is None:
            return rows
        return [r for r in rows if (r.get("hit_rate") or 0) >= min_hit_rate]

    def coin_predictions(self, symbol: str) -> list[dict[str, Any]]:
        sql = """
            SELECT p.*, c.symbol, v.actual_direction, v.is_correct, v.actual_magnitude,
                   v.reference_price, v.realized_price, v.validated_at,
                   pt.status AS trade_status, pt.entry_price, pt.exit_price, pt.pnl_usdt, pt.pnl_pct,
                   pt.side, pt.opened_at, pt.closed_at
            FROM predictions p
            JOIN coins c ON c.id = p.coin_id
            LEFT JOIN validations v ON v.prediction_id = p.id
            LEFT JOIN paper_trades pt ON pt.prediction_id = p.id
            WHERE c.symbol = :symbol
            ORDER BY p.predicted_at DESC
            LIMIT 50
        """
        with self.engine.begin() as conn:
            return [_serialize_row(dict(r)) for r in conn.execute(text(sql), {"symbol": symbol.upper()}).mappings().all()]

    def open_paper(self, payload: dict[str, Any]) -> UUID:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO paper_trades (
                        coin_id, prediction_id, symbol, side, source, margin_usdt, leverage,
                        notional_usdt, entry_price, qty, status, hold_minutes
                    ) VALUES (
                        :coin_id, :prediction_id, :symbol, :side, :source, :margin_usdt, :leverage,
                        :notional_usdt, :entry_price, :qty, 'open', :hold_minutes
                    ) RETURNING id
                    """
                ),
                payload,
            ).one()
            return row.id

    def close_due_paper(self, prediction_id: UUID, exit_price: float) -> None:
        with self.engine.begin() as conn:
            open_row = conn.execute(
                text("SELECT * FROM paper_trades WHERE prediction_id = :pid AND status = 'open'"),
                {"pid": prediction_id},
            ).mappings().first()
            if not open_row:
                return
            entry = float(open_row["entry_price"])
            qty = float(open_row["qty"])
            side = open_row["side"]
            signed = (exit_price - entry) if side == "UP" else (entry - exit_price)
            pnl = signed * qty
            notional = float(open_row["notional_usdt"]) or 1.0
            pnl_pct = pnl / notional
            conn.execute(
                text(
                    """
                    UPDATE paper_trades
                    SET exit_price = :exit_price, pnl_usdt = :pnl, pnl_pct = :pnl_pct,
                        is_full_loss = :full_loss, status = 'closed', closed_at = now()
                    WHERE id = :id
                    """
                ),
                {
                    "exit_price": exit_price,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "full_loss": pnl_pct <= -0.9,
                    "id": open_row["id"],
                },
            )

    def live_snapshot(self) -> dict[str, Any]:
        with self.engine.begin() as conn:
            pred = conn.execute(text("SELECT COUNT(*) AS n FROM predictions")).scalar_one()
            val = conn.execute(text("SELECT COUNT(*) AS n FROM validations")).scalar_one()
            open_t = conn.execute(text("SELECT COUNT(*) AS n FROM paper_trades WHERE status='open'")).scalar_one()
            hb = conn.execute(text("SELECT value FROM system_configuration WHERE key='worker_heartbeat'")).scalar()
        return {
            "predictions": int(pred or 0),
            "validations": int(val or 0),
            "open_setups": int(open_t or 0),
            "heartbeat": hb if isinstance(hb, dict) else json.loads(hb) if hb else None,
        }
