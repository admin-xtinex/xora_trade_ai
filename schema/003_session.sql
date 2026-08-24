ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS tp_price DOUBLE PRECISION;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS sl_price DOUBLE PRECISION;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS exit_reason TEXT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS entry_reason TEXT;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS analysis JSONB;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS session_id UUID;
ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS bucket TEXT;

CREATE TABLE IF NOT EXISTS trade_sessions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status        TEXT NOT NULL,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    warmup_until  TIMESTAMPTZ NOT NULL,
    ends_at       TIMESTAMPTZ NOT NULL,
    universe      JSONB,
    notes         TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_status ON trade_sessions (status, started_at DESC);
