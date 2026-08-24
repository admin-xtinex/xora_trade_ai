# Database schema

PostgreSQL 16. Normalized. Raw events preserved. Aggregates are derived.

Logical entities from the brief, mapped to tables:

| Entity | Table |
|---|---|
| coins | `coins` |
| market_snapshots | `market_snapshots` |
| feature_sets | `feature_sets` + `feature_set_items` |
| predictions | `predictions` |
| prediction_modules | `prediction_modules` |
| validations | `validations` |
| rolling_scores | `rolling_scores` |
| qualified_coins | `qualified_coins` |
| module_registry | `module_registry` |
| system_configuration | `system_configuration` |

Authoritative SQL: `schema/001_init.sql`.

## Relationships

```
coins 1---* market_snapshots 1---* feature_sets 1---* feature_set_items
                                \n                                 *--- predictions 1---* prediction_modules
                                                   \n                                                    *--- validations
coins 1---* rolling_scores
coins 1---* qualified_coins
```

## Notes

- `market_snapshots.payload` stores provider-normalized JSON (and a hash) so features can be recomputed.
- `feature_set_items` is the Feature Store grain: one row per module per set.
- `predictions` carry the experiment identity tuple.
- `validations` store direction, actual, magnitude error, confidence, calibration bucket, regime, timestamps — not a boolean win flag alone.
- `rolling_scores` are *materialized* views of history, keyed by coin + window + experiment. They can be truncated and rebuilt.
- `qualified_coins` is a point-in-time output of the generator, not a status flag on `coins`.
- UUIDs as primary keys. `TIMESTAMPTZ` everywhere.
- Soft uniqueness: one open prediction per (coin, horizon, strategy, experiment) can be enforced later if needed; Phase 1 allows multiple experiments concurrently.
