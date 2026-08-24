from __future__ import annotations

from xora.domain.enums import Direction
from xora.domain.models import FeatureResult, MarketSnapshot, ModuleConfig
from xora.modules import primitives as P


def _hint_from_score(bull: float, bear: float) -> tuple[Direction, float]:
    if bull > bear + 5:
        return Direction.UP, min(0.95, 0.5 + bull / 200)
    if bear > bull + 5:
        return Direction.DOWN, min(0.95, 0.5 + bear / 200)
    return Direction.NEUTRAL, 0.5


class TrendModule:
    key = "trend"
    version = "0.1.0"

    def analyze(self, snapshot: MarketSnapshot, config: ModuleConfig) -> FeatureResult:
        cfg = config.configuration
        fast = int(cfg.get("ema_fast", 20))
        slow = int(cfg.get("ema_slow", 50))
        e_fast = P.ema(snapshot.closes, fast)
        e_slow = P.ema(snapshot.closes, slow)
        a, b = e_fast[-1], e_slow[-1]
        if a is None or b is None:
            return FeatureResult(self.key, self.version, {}, error="insufficient candles")
        up = a > b
        hint = Direction.UP if up else Direction.DOWN
        return FeatureResult(
            self.key,
            self.version,
            {"ema_fast": a, "ema_slow": b, "trend_up": up},
            confidence=0.62,
            direction_hint=hint,
            rationale="EMA fast above slow" if up else "EMA fast below slow",
        )


class MomentumModule:
    key = "momentum"
    version = "0.1.0"

    def analyze(self, snapshot: MarketSnapshot, config: ModuleConfig) -> FeatureResult:
        closes = snapshot.closes
        if len(closes) < 20:
            return FeatureResult(self.key, self.version, {}, error="insufficient candles")
        change = (closes[-1] - closes[-10]) / closes[-10] if closes[-10] else 0.0
        hint = Direction.UP if change > 0.004 else Direction.DOWN if change < -0.004 else Direction.NEUTRAL
        return FeatureResult(
            self.key,
            self.version,
            {"roc_10": change},
            confidence=min(0.9, 0.5 + abs(change) * 20),
            direction_hint=hint,
            rationale=f"10-bar change {change:.3%}",
        )


class VolatilityModule:
    key = "volatility"
    version = "0.1.0"

    def analyze(self, snapshot: MarketSnapshot, config: ModuleConfig) -> FeatureResult:
        closes = snapshot.closes
        if len(closes) < 21:
            return FeatureResult(self.key, self.version, {}, error="insufficient candles")
        rets = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(-20, 0)]
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / len(rets)
        vol = var ** 0.5
        return FeatureResult(
            self.key,
            self.version,
            {"realized_vol_20": vol},
            confidence=0.4,
            direction_hint=Direction.NEUTRAL,
            rationale="realized volatility context only",
        )


class VolumeModule:
    key = "volume"
    version = "0.1.0"

    def analyze(self, snapshot: MarketSnapshot, config: ModuleConfig) -> FeatureResult:
        lookback = int(config.configuration.get("lookback", 20))
        vols = [c.volume for c in snapshot.candles]
        if len(vols) < lookback + 1:
            return FeatureResult(self.key, self.version, {}, error="insufficient candles")
        avg = sum(vols[-lookback - 1 : -1]) / lookback
        ratio = vols[-1] / avg if avg else 1.0
        last = snapshot.candles[-1]
        bullish = last.close >= last.open
        hint = Direction.NEUTRAL
        if ratio > 1.4:
            hint = Direction.UP if bullish else Direction.DOWN
        return FeatureResult(
            self.key,
            self.version,
            {"volume_ratio": ratio},
            confidence=min(0.85, 0.45 + max(ratio - 1, 0) * 0.2),
            direction_hint=hint,
            rationale=f"volume ratio {ratio:.2f}",
        )


class RsiModule:
    key = "rsi"
    version = "0.1.0"

    def analyze(self, snapshot: MarketSnapshot, config: ModuleConfig) -> FeatureResult:
        period = int(config.configuration.get("period", 14))
        value = P.rsi(snapshot.closes, period)
        if value is None:
            return FeatureResult(self.key, self.version, {}, error="insufficient candles")
        if value < 30:
            hint, conf = Direction.UP, 0.7
        elif value > 70:
            hint, conf = Direction.DOWN, 0.7
        else:
            hint, conf = Direction.NEUTRAL, 0.45
        return FeatureResult(self.key, self.version, {"rsi": value}, conf, hint, f"RSI {value:.1f}")


class MacdModule:
    key = "macd"
    version = "0.1.0"

    def analyze(self, snapshot: MarketSnapshot, config: ModuleConfig) -> FeatureResult:
        cfg = config.configuration
        value = P.macd(
            snapshot.closes,
            int(cfg.get("fast", 12)),
            int(cfg.get("slow", 26)),
            int(cfg.get("signal", 9)),
        )
        if value is None:
            return FeatureResult(self.key, self.version, {}, error="insufficient candles")
        hint = Direction.UP if value["histogram"] > 0 else Direction.DOWN
        return FeatureResult(self.key, self.version, value, 0.6, hint, "MACD histogram sign")


class BollingerModule:
    key = "bollinger"
    version = "0.1.0"

    def analyze(self, snapshot: MarketSnapshot, config: ModuleConfig) -> FeatureResult:
        cfg = config.configuration
        bands = P.bollinger(snapshot.closes, int(cfg.get("period", 20)), float(cfg.get("std", 2.0)))
        if bands is None:
            return FeatureResult(self.key, self.version, {}, error="insufficient candles")
        price = snapshot.last_price
        width = bands["upper"] - bands["lower"] or 1.0
        pos = (price - bands["lower"]) / width
        if pos < 0.2:
            hint = Direction.UP
        elif pos > 0.8:
            hint = Direction.DOWN
        else:
            hint = Direction.NEUTRAL
        bands = {**bands, "position": pos}
        return FeatureResult(self.key, self.version, bands, 0.55, hint, f"BB position {pos:.2f}")


class AtrModule:
    key = "atr"
    version = "0.1.0"

    def analyze(self, snapshot: MarketSnapshot, config: ModuleConfig) -> FeatureResult:
        period = int(config.configuration.get("period", 14))
        value = P.atr(
            [c.high for c in snapshot.candles],
            [c.low for c in snapshot.candles],
            snapshot.closes,
            period,
        )
        if value is None:
            return FeatureResult(self.key, self.version, {}, error="insufficient candles")
        pct = value / snapshot.last_price if snapshot.last_price else 0.0
        return FeatureResult(
            self.key,
            self.version,
            {"atr": value, "atr_pct": pct},
            0.35,
            Direction.NEUTRAL,
            "ATR used as magnitude context",
        )


BUILTIN_MODULES = [
    TrendModule(),
    MomentumModule(),
    VolatilityModule(),
    VolumeModule(),
    RsiModule(),
    MacdModule(),
    BollingerModule(),
    AtrModule(),
]
