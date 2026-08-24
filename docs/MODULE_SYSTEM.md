# Module discovery, execution, and future AI integration

## 1. Module interface

Every analyzer implements:

```python
class Analyzer(Protocol):
    key: str
    version: str

    def analyze(self, snapshot: MarketSnapshot, config: ModuleConfig) -> FeatureResult:
        ...
```

`analyze()` is the only required entry. No analyzer calls another analyzer.

`ModuleConfig` always includes:

- `enabled: bool`
- `weight: float`
- `priority: int`
- `configuration: dict`  # module-specific knobs (periods, thresholds)

Changing lookback from 14 to 21 is a config change, not a code change.

## 2. Discovery

On worker start (and on config reload):

1. Read `config/modules.yaml` for enabled keys.
2. Import `xora.modules.<key>.module`.
3. Expect an attribute `MODULE: Analyzer` (or a factory `create(config)`).
4. Register in `ModuleRegistry` with key, version, weight, priority.
5. Persist/upsert `module_registry` rows (name, version, enabled, weight, checksum).

Discovery rules:

- Unknown YAML keys fail fast at startup.
- Missing `MODULE` object fails fast.
- Disabled modules are registered but not executed.
- Adding a module later = new package under `src/xora/modules/<key>/` + YAML entry. No edits to Decision Engine.

Optional later upgrade: entry-point based plugins (`xora.modules` group). Phase 1 uses package + YAML only.

## 3. Execution

Feature Extraction Pipeline, per coin, per cycle:

1. Load enabled modules sorted by `priority`.
2. Execute independently (thread/async pool allowed; isolation required).
3. A module failure records an error FeatureResult and does **not** abort siblings.
4. Aggregate FeatureResults into one `feature_sets` row + N child feature rows.
5. Hand the aggregated set to Decision Engine.

Decision Engine never re-runs module code. It reads stored features for that `feature_set_id`.

## 4. Per-prediction module contribution

When a prediction is written, the engine also writes `prediction_modules`:

| Field | Meaning |
|---|---|
| module_name | registry key |
| module_version | code version of that analyzer |
| weight | weight used in this experiment |
| confidence | module-local confidence |
| contribution | signed score contributed to the decision |
| decision | UP / DOWN / NEUTRAL / ABSTAIN |
| raw_features | JSON copy of that module's features |

Raw always wins. Aggregates are derived.

## 5. How future AI modules plug in without refactor

All future modules are still `analyze(snapshot, config) -> FeatureResult`.

| Module | Snapshot extras needed | FeatureResult examples |
|---|---|---|
| support_resistance | OHLCV window | zone prices, strengths, nearest S/R distance |
| news_sentiment | attached news bundle (selector/provider extra) | sentiment score, novelty |
| chart_pattern | OHLCV | pattern label, quality |
| vision_ai | chart image blob ref | pattern class, confidence |
| llm_reasoning | feature set summary + optional news | rationale, direction hint, confidence |
| order_book | book snapshot | imbalance, wall distance |
| funding_rate | derivatives metrics | funding, basis |
| liquidation | liquidations feed | recent liq imbalance |

Integration pattern for expensive modules:

1. Keep them **disabled** in the default YAML.
2. Coin Selector or a pre-rank step can mark `top_n` coins.
3. Module config `run_on: all | top_n` limits cost.
4. Features still land in the Feature Store.
5. Decision strategy `ensemble.hybrid_v1` may weight `llm_reasoning` higher without touching other modules.

Vision and LLM modules must not become the scan-loop default for the full universe. That lesson is already documented in `TRADING_ENGINE_V2_DESIGN.md` (rate-limit incident). The architecture encodes it as config (`run_on: top_n`), not as a special-case in the pipeline.

## 6. Decision strategies vs modules

Modules produce features. Strategies consume feature maps.

A new ML model is a **strategy** (and possibly a training job), not a module — unless the model is itself a feature extractor (embeddings). That distinction keeps the Feature Store stable while models churn.
