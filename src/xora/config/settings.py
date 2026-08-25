from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [here.parents[3], here.parents[2], Path.cwd()]:
        if (candidate / "config" / "modules.yaml").exists():
            return candidate
    return Path.cwd()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        default="postgresql+psycopg://xora:xora@localhost:5432/xora",
        alias="DATABASE_URL",
    )
    universe: str = Field(default="", alias="XORA_UNIVERSE")
    timeframe: str = Field(default="15m", alias="XORA_TIMEFRAME")
    horizon: str = Field(default="15m", alias="XORA_HORIZON")
    cycle_seconds: int = Field(default=45, alias="XORA_CYCLE_SECONDS")
    warmup_seconds: int = Field(default=300, alias="XORA_WARMUP_SECONDS")
    session_seconds: int = Field(default=900, alias="XORA_SESSION_SECONDS")
    universe_size: int = Field(default=20, alias="XORA_UNIVERSE_SIZE")
    paper_margin_usdt: float = Field(default=10.0, alias="XORA_PAPER_MARGIN")
    paper_leverage: int = Field(default=15, alias="XORA_PAPER_LEVERAGE")
    paper_hold_minutes: int = Field(default=15, alias="XORA_PAPER_HOLD_MINUTES")
    min_trades_per_session: int = Field(default=3, alias="XORA_MIN_TRADES")
    tp_pct: float = Field(default=0.012, alias="XORA_TP_PCT")
    sl_pct: float = Field(default=0.008, alias="XORA_SL_PCT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    binance_base_url: str = Field(default="https://api.binance.com", alias="BINANCE_BASE_URL")

    @property
    def root(self) -> Path:
        return _find_root()

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.universe.split(",") if s.strip()]

    def load_yaml(self, name: str) -> dict[str, Any]:
        path = self.root / "config" / name
        if not path.exists():
            return {}
        return yaml.safe_load(path.read_text()) or {}

    def default_config(self) -> dict[str, Any]:
        cfg = self.load_yaml("default.yaml")
        cfg.setdefault("timeframe", self.timeframe)
        cfg.setdefault("horizon", self.horizon)
        if self.symbols:
            cfg["universe"] = self.symbols
        return cfg

    def modules_config(self) -> dict[str, Any]:
        data = self.load_yaml("modules.yaml")
        return data.get("modules", data)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
