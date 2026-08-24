from __future__ import annotations


def ema(values: list[float], period: int) -> list[float | None]:
    if len(values) < period:
        return [None] * len(values)
    k = 2 / (period + 1)
    out: list[float | None] = [None] * len(values)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    for i in range(period, len(values)):
        prev = out[i - 1] or seed
        out[i] = values[i] * k + prev * (1 - k)
    return out


def rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 2:
        return None
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        if delta > 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(delta, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0.0)) / period
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def macd(closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, float] | None:
    if len(closes) < slow + signal:
        return None
    e_fast = ema(closes, fast)
    e_slow = ema(closes, slow)
    line = [
        (a - b) if a is not None and b is not None else None
        for a, b in zip(e_fast, e_slow)
    ]
    compact = [x for x in line if x is not None]
    if len(compact) < signal:
        return None
    sig = ema(compact, signal)
    last = compact[-1]
    last_sig = sig[-1]
    if last_sig is None:
        return None
    return {"macd": last, "signal": last_sig, "histogram": last - last_sig}


def bollinger(closes: list[float], period: int = 20, std_mult: float = 2.0) -> dict[str, float] | None:
    if len(closes) < period:
        return None
    window = closes[-period:]
    mean = sum(window) / period
    var = sum((x - mean) ** 2 for x in window) / period
    std = var ** 0.5
    return {
        "upper": mean + std_mult * std,
        "middle": mean,
        "lower": mean - std_mult * std,
        "std": std,
    }


def atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return sum(trs[-period:]) / period
