# Dependency graph

Allowed direction: left-to-right / outer-to-inner. A box may depend only on boxes to its right, plus shared domain types.

```
                    +-----------+     +-------------+
                    |  FastAPI  |     |   Worker    |
                    |  /api/v1  |     |  scheduler  |
                    +-----+-----+     +------+------+
                          |                  |
                          v                  v
                    +--------------------------------+
                    |         Application            |
                    |  run_cycle / validate / query  |
                    +----------------+---------------+
                                     |
          +--------------------------+---------------------------+
          |                          |                           |
          v                          v                           v
 +----------------+        +------------------+        +-------------------+
 | Coin Selector  |        | Market Data Svc  |        | Module Registry   |
 +--------+-------+        +--------+---------+        +---------+---------+
          |                         |                            |
          v                         v                            v
 +----------------+        +------------------+        +-------------------+
 | Selector impls |        | Data Normalizer  |        | Feature modules   |
 | (config/CMC..) |        +--------+---------+        | rsi, macd, ...    |
 +----------------+                 |                  +-------------------+
                                    v                            |
                           +------------------+                  |
                           | Market Provider  |                  |
                           | interface        |                  |
                           +--------+---------+                  |
                                    |                            |
                                    v                            |
                           +------------------+                  |
                           | Binance / Bybit  |                  |
                           +------------------+                  |
                                                                 |
                                                                 v
                                                        +----------------+
                                                        | Feature Store  |
                                                        +--------+-------+
                                                                 |
                                                                 v
                                                        +----------------+
                                                        | Decision Engine|
                                                        | (strategies)   |
                                                        +--------+-------+
                                                                 |
                                                                 v
                                                        +----------------+
                                                        | Prediction Store|
                                                        +--------+-------+
                                                                 |
                                                                 v
                                                        +----------------+
                                                        | Validation Eng. |
                                                        +--------+-------+
                                                                 |
                                                                 v
                                                        +----------------+
                                                        | Rolling Stats   |
                                                        +--------+-------+
                                                                 |
                                                                 v
                                                        +----------------+
                                                        | Qualified Coins |
                                                        +----------------+
```

## Forbidden edges

| From | To | Why forbidden |
|---|---|
| Decision Engine | Market Provider | Engine sees features only. |
| Decision Engine | `modules.rsi.calc` | Engine must not calculate indicators. |
| `modules.rsi` | `modules.macd` | No analyzer-to-analyzer coupling. |
| FastAPI router | Binance client | API is a read/admin surface. |
| FastAPI router | Decision Engine | Cycles belong to the worker. |
| Feature module | SQLAlchemy session | Modules return FeatureResult; persistence is application/infra. |
| Domain | FastAPI / ccxt / SQLAlchemy | Domain stays portable. |

## Process coupling

```
api  --------read/write config----->  postgres
worker --heavy read/write cycle---->  postgres
api  X--does not call--> worker process memory
worker X--does not serve--> HTTP (except optional debug)
```

Shared database, separate processes, no in-process scheduler inside FastAPI.
