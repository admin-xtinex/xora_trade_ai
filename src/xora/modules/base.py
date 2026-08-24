from __future__ import annotations

from typing import Protocol

from xora.domain.models import FeatureResult, MarketSnapshot, ModuleConfig


class Analyzer(Protocol):
    key: str
    version: str

    def analyze(self, snapshot: MarketSnapshot, config: ModuleConfig) -> FeatureResult:
        ...
