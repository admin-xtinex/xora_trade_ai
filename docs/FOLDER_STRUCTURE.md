# Folder structure

Target layout after implementation. Phase 1 commits only documentation and schema drafts until approval.

```
xora_trade_ai/
  README.md
  pyproject.toml
  alembic.ini
  docker-compose.yml
  Dockerfile.api
  Dockerfile.worker
  .env.example
  config/
    default.yaml
    modules.yaml
    experiments.yaml
  schema/
    001_init.sql
  alembic/
    env.py
    versions/
  src/
    xora/
      __init__.py
      main.py                      # FastAPI factory (API process only)
      worker.py                    # worker entrypoint
      domain/
        __init__.py
        models.py                  # dataclasses / entities
        enums.py
        ports.py                   # MarketProvider, CoinSelector, clocks, stores
        feature.py                 # FeatureResult contract
        prediction.py
        validation.py
      application/
        __init__.py
        run_cycle.py
        validate_due.py
        qualify_coins.py
        rolling_stats.py
        queries.py
      modules/
        __init__.py
        base.py                    # Analyzer protocol: analyze() -> FeatureResult
        registry.py
        trend/
          __init__.py
          module.py
        momentum/
        volatility/
        volume/
        rsi/
        macd/
        bollinger/
        atr/
        # future drop-in packages:
        # support_resistance/, news_sentiment/, chart_pattern/
        # vision_ai/, llm_reasoning/, order_book/, funding_rate/, liquidation/
      decision/
        __init__.py
        engine.py                  # selects strategy, never computes indicators
        strategies/
          base.py
          weighted_rules.py
      market/
        __init__.py
        service.py
        normalizer.py
        providers/
          base.py
          binance.py
        selectors/
          base.py
          configured_universe.py
      persistence/
        __init__.py
        db.py
        models.py                  # SQLAlchemy models
        repositories/
          coins.py
          snapshots.py
          features.py
          predictions.py
          validations.py
          scores.py
          qualified.py
          modules.py
          config.py
      api/
        __init__.py
        deps.py
        v1/
          router.py
          coins.py
          snapshots.py
          features.py
          predictions.py
          validations.py
          scores.py
          qualified.py
          modules.py
          health.py
      config/
        settings.py
      observability/
        logging.py
  tests/
    unit/
    integration/
    contracts/                     # module interface + provider contract tests
  docs/
    ...
```

## Why this shape

- `modules/` is a plugin directory. Adding `modules/funding_rate/module.py` plus a YAML flag is the intended extension path.
- `decision/` cannot import `modules.rsi` internals.
- `api/` cannot import provider SDKs except through application query services.
- `worker.py` and `main.py` are separate process entrypoints sharing the same application layer.
