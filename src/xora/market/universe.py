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
    "FETUSDT", "RENDERUSDT", "WIFUSDT", "TIAUSDT", "SEIUSDT",
    "BCHUSDT", "ETCUSDT", "XLMUSDT", "HBARUSDT", "ICPUSDT",
    "IMXUSDT", "STXUSDT", "RUNEUSDT", "GRTUSDT", "MKRUSDT",
    "LDOUSDT", "QNTUSDT", "EGLDUSDT", "ALGOUSDT", "VETUSDT",
    "SANDUSDT", "MANAUSDT", "AXSUSDT", "GALAUSDT", "WLDUSDT",
]


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
        self.base_url = get_settings().binance_base_url.rstrip("/")

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
        if len(tickers) < 50:
            have = {t["symbol"] for t in tickers}
            for symbol in FALLBACK:
                if symbol not in have:
                    tickers.append({"symbol": symbol, "change_pct": 0.0, "quote_volume": 0.0, "last_price": 0.0})
        by_change = sorted(tickers, key=lambda r: r["change_pct"], reverse=True)
        by_volume = sorted(tickers, key=lambda r: r["quote_volume"], reverse=True)
        by_move = sorted(tickers, key=lambda r: abs(r["change_pct"]), reverse=True)
        used: set[str] = set()
        picks: list[UniversePick] = []

        def take(rows: list[dict], bucket: str, n: int) -> None:
            for row in rows:
                if len([p for p in picks if p.bucket == bucket]) >= n:
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

        take(by_change, "gainers", 10)
        take(list(reversed(by_change)), "losers", 10)
        take(by_move, "movers", 10)
        take(by_volume, "volume", 10)
        ai_pool = [r for r in by_volume if r["symbol"] not in used]
        take(ai_pool or by_volume, "ai", 10)
        if len(picks) < 50:
            take(tickers, "ai", 50 - len(picks))
        return picks[:50]
