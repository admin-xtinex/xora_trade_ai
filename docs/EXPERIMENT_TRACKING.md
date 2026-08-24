# Experiments and engine-version tracking

Every prediction is an experiment observation. If a row cannot be traced to the exact code + config + features that produced it, it is incomplete.

## 1. Identity tuple

Stored on `predictions`:

| Field | Source |
|---|---|
| `engine_version` | package version / git SHA (worker stamps at cycle start) |
| `strategy_name` | e.g. `rules.weighted_v1` |
| `model_name` | `none` for rules; artifact name for ML/LLM |
| `feature_version` | hash of enabled module keys + module versions |
| `config_version` | hash of modules.yaml + strategy config used |
| `experiment_name` | optional label, default `production` |

`feature_sets` also stores `feature_version` so a prediction can join back to the exact feature payload.

## 2. Why hashes, not only names

Names change slowly. Weights, RSI periods, and enabled flags change often. A SHA-256 over the canonical JSON of:

- enabled modules, versions, weights, priorities, knobs
- strategy name + strategy knobs
- engine git SHA

…is `config_version`. Two predictions with the same `strategy_name` but different RSI periods must not share a config_version.

## 3. Comparison workflow (future, schema-ready now)

```
rules.weighted_v1   vs   ml.sklearn_v1   vs   llm.reasoner_v1
        ↓                        ↓                    ↓
   same coin list, same snapshots (or same feature_sets)
        ↓
   validations joined by prediction_id
        ↓
   rolling_scores grouped by (strategy_name, model_name, config_version)
```

Phase 1 does not need an experiment UI. It needs the columns and the discipline to fill them.

## 4. Module-level replay

Because `prediction_modules.raw_features` is stored:

- a new strategy can be scored offline against historical feature sets
- module weights can be re-fit without re-fetching Binance
- a broken module version can be excluded from later aggregates

Recompute path:

1. Select `feature_sets` for a date range.
2. Run a candidate strategy in-process (batch job, still not the API).
3. Write predictions with a distinct `experiment_name`.
4. If outcomes already exist for that horizon, attach validations by snapshot time + coin + horizon — or re-validate from stored prices.

## 5. Versioning policy

- Module `version` increments when feature keys or semantics change.
- Strategy `version` increments when scoring math changes.
- Patch-level code that does not change outputs does not require a feature_version bump, but git SHA still lands on `engine_version`.

## 6. Production vs shadow

Config flag `experiments.shadow_strategies: []` lets the worker run extra strategies in the same cycle and persist them with `experiment_name=shadow:<strategy>` without affecting `qualified_coins`.

Qualified Coin Generator reads only `experiment_name` in `{production, default}` unless configured otherwise.
