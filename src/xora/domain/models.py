from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from xora.domain.enums import Direction


@dataclass
class Candle:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class MarketSnapshot:
    coin_id: UUID | None
    symbol: str
    venue: str
    timeframe: str
    as_of: datetime
    candles: list[Candle]
    ticker: dict[str, Any] | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def closes(self) -> list[float]:
        return [c.close for c in self.candles]

    @property
    def last_price(self) -> float:
        return self.candles[-1].close if self.candles else 0.0


@dataclass
class ModuleConfig:
    enabled: bool = True
    weight: float = 1.0
    priority: int = 100
    configuration: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeatureResult:
    module_key: str
    module_version: str
    features: dict[str, Any]
    confidence: float | None = None
    direction_hint: Direction = Direction.NONE
    rationale: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ModuleContribution:
    module_name: str
    module_version: str
    weight: float
    confidence: float | None
    contribution: float
    decision: str | None
    raw_features: dict[str, Any]


@dataclass
class DecisionResult:
    direction: Direction
    confidence: float
    score: float
    magnitude: float | None
    market_regime: str | None
    contributions: list[ModuleContribution]
    metadata: dict[str, Any] = field(default_factory=dict)
