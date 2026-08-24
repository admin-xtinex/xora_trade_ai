from __future__ import annotations

from typing import Any


def compute_pnl(side: str, entry_price: float, exit_price: float, qty: float, margin_usdt: float, leverage: int) -> dict[str, Any]:
    entry_price = float(entry_price)
    exit_price = float(exit_price)
    qty = float(qty)
    margin_usdt = float(margin_usdt or 10)
    leverage = int(leverage or 15)
    notional = margin_usdt * leverage
    price_move = exit_price - entry_price
    signed_move = price_move if side == "UP" else (entry_price - exit_price)
    pnl_usdt = signed_move * qty
    formula = "(exit - entry) * qty" if side == "UP" else "(entry - exit) * qty"
    expected_qty = (notional / entry_price) if entry_price else 0.0
    qty_matches = abs(qty - expected_qty) <= max(1e-8, expected_qty * 1e-6)
    recomputed = signed_move * qty
    return {
        "side": side,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "qty": qty,
        "margin_usdt": margin_usdt,
        "leverage": leverage,
        "notional_usdt": notional,
        "price_move": price_move,
        "signed_move": signed_move,
        "pnl_usdt": pnl_usdt,
        "pnl_pct_margin": pnl_usdt / margin_usdt if margin_usdt else 0.0,
        "pnl_pct_notional": pnl_usdt / notional if notional else 0.0,
        "formula": formula,
        "worked_example": f"{formula} = {signed_move:.8f} * {qty:.8f} = {pnl_usdt:.8f} USDT",
        "qty_formula": "qty = (margin * leverage) / entry = notional / entry",
        "qty_expected": expected_qty,
        "qty_matches_notional": qty_matches,
        "recomputed_pnl": recomputed,
        "proof_ok": abs(recomputed - pnl_usdt) < 1e-8 and qty_matches,
    }
