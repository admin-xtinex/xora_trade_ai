ALTER TABLE paper_trades ADD COLUMN IF NOT EXISTS engine_name TEXT;
CREATE INDEX IF NOT EXISTS idx_paper_engine ON paper_trades (engine_name, status);
