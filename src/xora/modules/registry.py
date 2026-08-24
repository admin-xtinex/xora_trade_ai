from __future__ import annotations

import hashlib
from dataclasses import dataclass

from xora.config.settings import canonical_json, get_settings
from xora.domain.models import FeatureResult, MarketSnapshot, ModuleConfig
from xora.modules.builtins import BUILTIN_MODULES
from xora.persistence.store import Store


@dataclass
class RegisteredModule:
    analyzer: object
    config: ModuleConfig


class ModuleRegistry:
    def __init__(self, store: Store | None = None) -> None:
        self.store = store or Store()
        self.modules: list[RegisteredModule] = []
        self.reload()

    def reload(self) -> None:
        settings = get_settings()
        raw = settings.modules_config()
        catalog = {m.key: m for m in BUILTIN_MODULES}
        loaded: list[RegisteredModule] = []
        for key, spec in raw.items():
            if key not in catalog:
                continue
            cfg = ModuleConfig(
                enabled=bool(spec.get("enabled", False)),
                weight=float(spec.get("weight", 1.0)),
                priority=int(spec.get("priority", 100)),
                configuration=spec.get("configuration") or {},
            )
            analyzer = catalog[key]
            loaded.append(RegisteredModule(analyzer=analyzer, config=cfg))
            self.store.upsert_module(
                name=key,
                version=analyzer.version,
                enabled=cfg.enabled,
                weight=cfg.weight,
                priority=cfg.priority,
                configuration=cfg.configuration,
                checksum=hashlib.sha256(canonical_json(spec).encode()).hexdigest()[:16],
            )
        self.modules = sorted(loaded, key=lambda m: m.config.priority)

    @property
    def enabled(self) -> list[RegisteredModule]:
        return [m for m in self.modules if m.config.enabled]

    def feature_version(self) -> str:
        payload = [
            {"key": m.analyzer.key, "version": m.analyzer.version}
            for m in self.enabled
        ]
        return hashlib.sha256(canonical_json(payload).encode()).hexdigest()[:16]

    def config_version(self) -> str:
        payload = [
            {
                "key": m.analyzer.key,
                "weight": m.config.weight,
                "priority": m.config.priority,
                "configuration": m.config.configuration,
            }
            for m in self.enabled
        ]
        return hashlib.sha256(canonical_json(payload).encode()).hexdigest()[:16]

    def extract(self, snapshot: MarketSnapshot) -> list[FeatureResult]:
        results: list[FeatureResult] = []
        for item in self.enabled:
            try:
                results.append(item.analyzer.analyze(snapshot, item.config))
            except Exception as exc:  # noqa: BLE001 — isolate module failures
                results.append(
                    FeatureResult(
                        module_key=item.analyzer.key,
                        module_version=item.analyzer.version,
                        features={},
                        error=str(exc),
                    )
                )
        return results
