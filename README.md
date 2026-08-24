# XORA Prediction AI

Independent AI prediction platform. Analyzes markets, extracts features, produces predictions, validates outcomes, and measures reliability. It does **not** execute trades.

## Run locally (Docker)

Needs Docker Desktop (or Docker Engine + Compose v2) and internet access so the worker can read public Binance klines.

```bash
git clone https://github.com/admin-xtinex/xora_trade_ai.git
cd xora_trade_ai
docker compose up --build
```

That starts:

- PostgreSQL 16 on `localhost:5432`
- API on [http://localhost:8000](http://localhost:8000)
- Worker that runs a prediction cycle immediately, then every 5 minutes

Open interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### First cycle by hand

```bash
curl -X POST http://localhost:8000/api/v1/admin/cycles
curl http://localhost:8000/api/v1/predictions
curl http://localhost:8000/api/v1/modules
```

Useful routes:

| Method | Path |
|---|---|
| GET | `/api/v1/health` |
| GET | `/api/v1/predictions` |
| GET | `/api/v1/predictions/{id}` |
| GET | `/api/v1/qualified-coins` |
| GET | `/api/v1/validations` |
| POST | `/api/v1/admin/cycles` |

Validation rows appear after the prediction horizon (default 15m). Until then `/validations` and `/qualified-coins` stay empty.

### Optional pgAdmin

```bash
docker compose --profile dev up --build
```

Then open [http://localhost:5050](http://localhost:5050) (`admin@xora.local` / `admin`). Host name inside Compose is `postgres`.

### Reset the database

```bash
docker compose down -v
docker compose up --build
```

## Run without rebuilding the app containers

If you already have Postgres from Compose and Python 3.12 locally:

```bash
docker compose up -d postgres
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
export DATABASE_URL=postgresql+psycopg://xora:xora@localhost:5432/xora
uvicorn xora.main:app --reload --port 8000
# another terminal:
python -m xora.worker
```

Default universe: `BTCUSDT,ETHUSDT,SOLUSDT`. Override with `XORA_UNIVERSE`.

## Architecture docs

See `docs/` for the Phase 1 design. `TRADING_ENGINE_V2_DESIGN.md` is historical only.
