from __future__ import annotations

from datetime import datetime, timezone

import httpx

from xora.config.settings import get_settings
from xora.domain.models import Candle, MarketSnapshot


class BinanceMarketProvider:
    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.binance_base_url).rstrip("/")

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 120) -> MarketSnapshot:
        url = f"{self.base_url}/api/v3/klines"
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, params={"symbol": symbol, "interval": timeframe, "limit": limit})
            response.raise_for_status()
            raw = response.json()
        candles = [
            Candle(
                time=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in raw
        ]
        as_of = datetime.fromtimestamp(candles[-1].time / 1000, tz=timezone.utc) if candles else datetime.now(timezone.utc)
        return MarketSnapshot(
            coin_id=None,
            symbol=symbol,
            venue="binance",
            timeframe=timeframe,
            as_of=as_of,
            candles=candles,
        )

    def fetch_last_price(self, symbol: str) -> float:
        url = f"{self.base_url}/api/v3/ticker/price"
        with httpx.Client(timeout=15.0) as client:
            response = client.get(url, params={"symbol": symbol})
            response.raise_for_status()
            return float(response.json()["price"])
