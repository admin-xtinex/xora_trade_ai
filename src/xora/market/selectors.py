from __future__ import annotations

from xora.config.settings import get_settings


class ConfiguredUniverseSelector:
    def select(self) -> list[str]:
        return get_settings().symbols
