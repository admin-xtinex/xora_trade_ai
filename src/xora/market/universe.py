from __future__ import annotations

from dataclasses import dataclass

import httpx

from xora.config.settings import get_settings

FALLBACK = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "TRXUSDT", "TONUSDT", "NEARUSDT", "LTCUSDT", "ATOMUSDT",
    "SUIUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "PEPEUSDT",
    "SHIBUSDT", "UNIUSDT", "AAVEUSDT", "FILUSDT", "INJUSDT",
]

PER_BUCKET = 5
UNIVERSE_SIZE = 25


@dataclass
class UniversePick:
    symbol: str
    bucket: str
    change_pct: float
    quote_volume: float
    last_price: float


def _usable(symbol: str) -> bool:
    if not symbol.endswith("USDT"):
        return False
    if symbol.endswith(("UPUSDT", "DOWNUSDT")):
        return False
    if "BULL" in symbol or "BEAR" in symbol:
        return False
    return True


class BinanceUniverseBuilder:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.binance_base_url.rstrip("/")
        self.size = int(settings.universe_size or UNIVERSE_SIZE)
        self.per_bucket = max(1, self.size // 5)

    def fetch_tickers(self) -> list[dict]:
        url = f"{self.base_url}/api/v3/ticker/24hr"
        with httpx.Client(timeout=25.0) as client:
            response = client.get(url)
            response.raise_for_status()
            rows = response.json()
        out = []
        for row in rows:
            symbol = row.get("symbol") or ""
            if not _usable(symbol):
                continue
            out.append(
                {
                    "symbol": symbol,
                    "change_pct": float(row.get("priceChangePercent") or 0),
                    "quote_volume": float(row.get("quoteVolume") or 0),
                    "last_price": float(row.get("lastPrice") or 0),
                }
            )
        return out

    def build(self) -> list[UniversePick]:
        try:
            tickers = self.fetch_tickers()
        except Exception:
            tickers = []
        if len(tickers) < self.size:
            have = {t["symbol"] for t in tickers}
            for symbol in FALLBACK:
                if symbol not in have:
                    tickers.append({"symbol": symbol, "change_pct": 0.0, "quote_volume": 0.0, "last_price": 0.0})
        by_change = sorted(tickers, key=lambda r: r["change_pct"], reverse=True)
        by_volume = sorted(tickers, key=lambda r: r["quote_volume"], reverse=True)
        by_move = sorted(tickers, key=lambda r: abs(r["change_pct"]), reverse=True)
        used: set[str] = set()
        picks: list[UniversePick] = []
        n = self.per_bucket

        def take(rows: list[dict], bucket: str, count: int) -> None:
            for row in rows:
                if len([p for p in picks if p.bucket == bucket]) >= count:
                    break
                if row["symbol"] in used:
                    continue
                used.add(row["symbol"])
                picks.append(
                    UniversePick(
                        symbol=row["symbol"],
                        bucket=bucket,
                        change_pct=row["change_pct"],
                        quote_volume=row["quote_volume"],
                        last_price=row["last_price"],
                    )
                )

        take(by_change, "gainers", n)
        take(list(reversed(by_change)), "losers", n)
        take(by_move, "movers", n)
        take(by_volume, "volume", n)
        take([r for r in by_volume if r["symbol"] not in used] or by_volume, "ai", n)
        if len(picks) < self.size:
            take(tickers, "ai", self.size - len(picks))
        return picks[: self.size]
