CREATE TABLE IF NOT EXISTS paper_trades (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coin_id          UUID NOT NULL REFERENCES coins(id),
    prediction_id    UUID REFERENCES predictions(id),
    symbol           TEXT NOT NULL,
    side             TEXT NOT NULL,
    source           TEXT,
    margin_usdt      DOUBLE PRECISION NOT NULL,
    leverage         INTEGER NOT NULL,
    notional_usdt    DOUBLE PRECISION NOT NULL,
    entry_price      DOUBLE PRECISION NOT NULL,
    exit_price       DOUBLE PRECISION,
    qty              DOUBLE PRECISION NOT NULL,
    pnl_usdt         DOUBLE PRECISION,
    pnl_pct          DOUBLE PRECISION,
    is_full_loss     BOOLEAN NOT NULL DEFAULT FALSE,
    status           TEXT NOT NULL DEFAULT 'open',
    opened_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at        TIMESTAMPTZ,
    hold_minutes     INTEGER NOT NULL DEFAULT 5
);

CREATE INDEX IF NOT EXISTS idx_paper_status ON paper_trades (status, opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_paper_symbol ON paper_trades (symbol, opened_at DESC);

CREATE TABLE IF NOT EXISTS universe_picks (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol           TEXT NOT NULL,
    source           TEXT NOT NULL,
    change_pct       DOUBLE PRECISION,
    quote_volume     DOUBLE PRECISION,
    last_price       DOUBLE PRECISION,
    picked_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_universe_picked ON universe_picks (picked_at DESC);
