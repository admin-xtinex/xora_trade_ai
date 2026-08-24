-- XORA Prediction AI — Phase 1 schema draft
-- Not applied until architecture approval + Alembic implementation.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE coins (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol          TEXT NOT NULL,
    base_asset      TEXT NOT NULL,
    quote_asset     TEXT NOT NULL,
    venue           TEXT NOT NULL DEFAULT 'binance',
    instrument_type TEXT NOT NULL DEFAULT 'spot',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (venue, symbol, instrument_type)
);

CREATE TABLE market_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coin_id         UUID NOT NULL REFERENCES coins(id),
    venue           TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    as_of           TIMESTAMPTZ NOT NULL,
    ohlcv           JSONB NOT NULL,
    ticker          JSONB,
    order_book      JSONB,
    derivatives     JSONB,
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_hash    TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_snapshots_coin_asof ON market_snapshots (coin_id, as_of DESC);
CREATE INDEX idx_snapshots_tf_asof ON market_snapshots (timeframe, as_of DESC);

CREATE TABLE feature_sets (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coin_id          UUID NOT NULL REFERENCES coins(id),
    snapshot_id      UUID NOT NULL REFERENCES market_snapshots(id),
    feature_version  TEXT NOT NULL,
    config_version   TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_feature_sets_coin ON feature_sets (coin_id, created_at DESC);

CREATE TABLE feature_set_items (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feature_set_id   UUID NOT NULL REFERENCES feature_sets(id) ON DELETE CASCADE,
    module_name      TEXT NOT NULL,
    module_version   TEXT NOT NULL,
    features         JSONB NOT NULL,
    confidence       DOUBLE PRECISION,
    direction_hint   TEXT,
    rationale        TEXT,
    extras           JSONB NOT NULL DEFAULT '{}'::jsonb,
    error            TEXT,
    UNIQUE (feature_set_id, module_name)
);

CREATE TABLE predictions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coin_id          UUID NOT NULL REFERENCES coins(id),
    feature_set_id   UUID NOT NULL REFERENCES feature_sets(id),
    snapshot_id      UUID NOT NULL REFERENCES market_snapshots(id),
    direction        TEXT NOT NULL,
    horizon          TEXT NOT NULL,
    magnitude        DOUBLE PRECISION,
    confidence       DOUBLE PRECISION NOT NULL,
    score            DOUBLE PRECISION,
    market_regime    TEXT,
    engine_version   TEXT NOT NULL,
    strategy_name    TEXT NOT NULL,
    model_name       TEXT NOT NULL DEFAULT 'none',
    feature_version  TEXT NOT NULL,
    config_version   TEXT NOT NULL,
    experiment_name  TEXT NOT NULL DEFAULT 'production',
    predicted_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    horizon_at       TIMESTAMPTZ NOT NULL,
    metadata         JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_predictions_coin ON predictions (coin_id, predicted_at DESC);
CREATE INDEX idx_predictions_exp ON predictions (experiment_name, strategy_name, predicted_at DESC);
CREATE INDEX idx_predictions_due ON predictions (horizon_at);

CREATE TABLE prediction_modules (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prediction_id    UUID NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
    module_name      TEXT NOT NULL,
    module_version   TEXT NOT NULL,
    weight           DOUBLE PRECISION NOT NULL,
    confidence       DOUBLE PRECISION,
    contribution     DOUBLE PRECISION NOT NULL DEFAULT 0,
    decision         TEXT,
    raw_features     JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (prediction_id, module_name)
);

CREATE TABLE validations (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prediction_id        UUID NOT NULL UNIQUE REFERENCES predictions(id),
    predicted_direction  TEXT NOT NULL,
    actual_direction     TEXT NOT NULL,
    predicted_magnitude  DOUBLE PRECISION,
    actual_magnitude     DOUBLE PRECISION,
    magnitude_error      DOUBLE PRECISION,
    confidence           DOUBLE PRECISION NOT NULL,
    calibration_bucket   TEXT,
    market_regime        TEXT,
    is_correct           BOOLEAN NOT NULL,
    validated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    reference_price      DOUBLE PRECISION,
    realized_price       DOUBLE PRECISION,
    extras               JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE rolling_scores (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coin_id          UUID NOT NULL REFERENCES coins(id),
    window           TEXT NOT NULL,
    experiment_name  TEXT NOT NULL,
    strategy_name    TEXT NOT NULL,
    sample_size      INTEGER NOT NULL,
    hit_rate         DOUBLE PRECISION,
    avg_confidence   DOUBLE PRECISION,
    calibration_error DOUBLE PRECISION,
    avg_magnitude_error DOUBLE PRECISION,
    score            DOUBLE PRECISION,
    computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (coin_id, window, experiment_name, strategy_name)
);

CREATE TABLE qualified_coins (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coin_id          UUID NOT NULL REFERENCES coins(id),
    experiment_name  TEXT NOT NULL,
    strategy_name    TEXT NOT NULL,
    reason           TEXT,
    score            DOUBLE PRECISION NOT NULL,
    gates            JSONB NOT NULL DEFAULT '{}'::jsonb,
    qualified_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at       TIMESTAMPTZ,
    is_current       BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX idx_qualified_current ON qualified_coins (is_current, experiment_name);

CREATE TABLE module_registry (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module_name      TEXT NOT NULL UNIQUE,
    module_version   TEXT NOT NULL,
    enabled          BOOLEAN NOT NULL DEFAULT FALSE,
    weight           DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    priority         INTEGER NOT NULL DEFAULT 100,
    configuration    JSONB NOT NULL DEFAULT '{}'::jsonb,
    checksum         TEXT,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE system_configuration (
    key              TEXT PRIMARY KEY,
    value            JSONB NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
