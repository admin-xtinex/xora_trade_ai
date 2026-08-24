from __future__ import annotations

from xora.domain.enums import Direction
from xora.domain.models import DecisionResult, FeatureResult, ModuleConfig, ModuleContribution
from xora.modules.registry import RegisteredModule


class WeightedRulesStrategy:
    name = "rules.weighted_v1"

    def decide(
        self,
        results: list[FeatureResult],
        registered: list[RegisteredModule],
        force: bool = True,
        fallback_change: float | None = None,
    ) -> DecisionResult:
        weights = {item.analyzer.key: item.config for item in registered}
        contributions: list[ModuleContribution] = []
        score = 0.0
        weight_sum = 0.0
        atr_pct = None
        for result in results:
            cfg = weights.get(result.module_key, ModuleConfig())
            conf = result.confidence or 0.0
            signed = 0.0
            if result.direction_hint == Direction.UP:
                signed = cfg.weight * conf
            elif result.direction_hint == Direction.DOWN:
                signed = -cfg.weight * conf
            score += signed
            weight_sum += abs(cfg.weight)
            if "atr_pct" in result.features:
                atr_pct = float(result.features["atr_pct"])
            contributions.append(
                ModuleContribution(
                    module_name=result.module_key,
                    module_version=result.module_version,
                    weight=cfg.weight,
                    confidence=result.confidence,
                    contribution=signed,
                    decision=result.direction_hint.value if result.direction_hint else None,
                    raw_features=result.features,
                )
            )
        if score > 0.05:
            direction = Direction.UP
        elif score < -0.05:
            direction = Direction.DOWN
        else:
            direction = Direction.NEUTRAL
        forced = False
        if force and direction == Direction.NEUTRAL:
            forced = True
            if score > 0:
                direction = Direction.UP
            elif score < 0:
                direction = Direction.DOWN
            elif (fallback_change or 0) >= 0:
                direction = Direction.UP
            else:
                direction = Direction.DOWN
        confidence = min(0.95, max(abs(score) / max(weight_sum, 1e-6), 0.15 if forced else 0.0))
        magnitude = atr_pct * 1.5 if atr_pct is not None else None
        regime = "volatile" if (atr_pct or 0) > 0.02 else "normal"
        return DecisionResult(
            direction=direction,
            confidence=confidence,
            score=score,
            magnitude=magnitude,
            market_regime=regime,
            contributions=contributions,
            metadata={"strategy": self.name, "forced": forced},
        )


class DecisionEngine:
    def __init__(self) -> None:
        self.strategy = WeightedRulesStrategy()

    def decide(
        self,
        results: list[FeatureResult],
        registered: list[RegisteredModule],
        force: bool = True,
        fallback_change: float | None = None,
    ) -> DecisionResult:
        return self.strategy.decide(results, registered, force=force, fallback_change=fallback_change)
