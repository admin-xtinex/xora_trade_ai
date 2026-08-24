# XORA Prediction AI

Independent AI prediction platform. Analyzes markets, extracts features, produces predictions, validates outcomes, and measures reliability. It does **not** execute trades.

## Run locally

```bash
git clone https://github.com/admin-xtinex/xora_trade_ai.git
cd xora_trade_ai
git pull
docker compose up --build
```

Then open the UI:

**http://localhost:8000**

Also available:

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/v1/health

In the dashboard, click **Run cycle** to fetch Binance data, extract features, and write predictions. Validations appear after the 15m horizon.

### Reset DB

```bash
docker compose down -v
docker compose up --build
```
