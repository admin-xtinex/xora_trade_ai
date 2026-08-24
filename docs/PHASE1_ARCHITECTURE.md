# XORA Prediction AI — Phase 1 Architecture

**Status:** DESIGN for review. No production implementation until approved.  
**Repo:** `admin-xtinex/xora_trade_ai`  
**Date:** 2026-08-25  
**Constraint:** this platform must never place, approve, or manage trades.

---

## 0. Product boundary

XORA is an **independent AI Prediction Platform**, not a trading bot.

```
Market Analysis
    ↓
Feature Extraction
    ↓
Decision Making
    ↓
Prediction
    ↓
Validation
    ↓
Reliability Measurement
    ↓
Qualified Coin Generation
```

Out of scope for this service:

- order placement, cancel, or amend
- `/approve` execution flows
- position sizing, SL/TP construction as trade instructions
- trade-guardian / session monitors
- exchange API keys for trading
- paper or live execution adapters

Those belong to a future *consumer* of qualified predictions, not this codebase.

---

## 1. Reference-bot analysis (read-only)

Sources reviewed:

| Source | What it is | Disposition |
|---|---|---|
| `admin-xtinex/xora_trade_ai` `TRADING_ENGINE_V2_DESIGN.md` | V2 trading-engine migration spec | Keep as historical reference. Reuse *ideas* (feature vs decision split, calibration, ranking), discard execution coupling. |
| `admin-xtinex/trading_bot` `xtinex-trading.jsx` | Single-file UI/engine monolith | Do not port. Extract conceptual analyzers only. |
| `admin-xtinex/trading_bot_app` | Capacitor client + Binance-hardcoded TA | Study indicator formulas and API shapes. Do not reuse architecture. |

### 1.1 What the reference systems actually do

The mobile app `src/services/technicalAnalysis.js` is the clearest existing “prediction” path:

1. Hardcoded Binance REST for klines.
2. Compute RSI, MACD, Bollinger, ATR, EMA trend, volume ratio **inside the same function**.
3. Immediately convert those numbers into BUY/SELL + confidence + TP/SL.
4. Rank symbols by how far confidence sits from 50.

`TRADING_ENGINE_V2_DESIGN.md` already identified the same structural problem at engine scale: discovery, scoring, validation, and execution live in one scan loop. V2 proposed demoting indicators to veto-only and adding market-wide ranking — but still emitted `/api/xora/approve` payloads into an unchanged execution stack.

### 1.2 Defects that must not be copied

| Defect | Where | Why it breaks a prediction platform |
|---|---|---|
| Indicators compute *and* decide | `analyzeSymbol()` | Decision Engine must consume features only. |
| Provider hardcoded to Binance | TA + marketData services | Provider must be an interface. |
| Coin universe hardcoded | `POPULAR_SYMBOLS` | Coin selection is an independent service. |
| No persisted features or per-module contribution | client-only / in-memory | Future recalculation and experiments require raw rows. |
| Validation is win/loss of a trade | V2 learning store tied to closes | Validation is directional/magnitude/calibration of a *prediction*. |
| SQLite / localStorage as system of record | app caches, design notes | PostgreSQL from day one. |
| Scheduler inside the web process | scan loop in server/UI | Worker service owns cycles. |
| Execution safety mixed with analysis | approve, guardian, cooldowns | Different product. |
| Uncalibrated confidence | V2 itself calls V1 confidence “famously uncalibrated” | Rolling statistics + validation schema must exist first. |

### 1.3 Ideas worth keeping (as concepts, not files)

- Separate structure / volume / momentum / volatility concerns into modules.
- Market-wide ranking instead of “every passer is a trade”.
- Persist full decision context for later calibration.
- Two-tier future predictor: cheap deterministic/ML for the universe, expensive LLM/vision only on top-N.
- Fetch costly vendor data (funding, OI, news) only after a candidate is selected.

Nothing from the reference bots is copied as production code in Phase 1.

---

## 2. Revised architecture

### 2.1 Layering (Clean Architecture)

```
+--------------------------- API ----------------------------+
|  FastAPI routers under /api/v1  (read models + admin)     |
+------------------------ Application -----------------------+
|  Use cases: run_cycle, validate_due, qualify_coins,        |
|  query predictions / scores / qualified set                |
+-------------------------- Domain --------------------------+
|  FeatureResult, Prediction, Validation, Module contract,   |
|  Decision strategy protocol, Coin, MarketSnapshot          |
+------------------------ Modules ---------------------------+
|  Feature modules discovered by Module Registry             |
+---------------------- Infrastructure ----------------------+
|  Market providers, Coin selectors, Postgres repos,         |
|  config loader, clock, HTTP clients, worker runtime        |
+------------------------------------------------------------+
```

Rules:

- Domain has no FastAPI, SQLAlchemy, or Binance imports.
- Application orchestrates; it does not compute RSI.
- Infrastructure implements ports defined in domain/application.
- Modules depend only on the module interface + normalized market data.
- Decision Engine depends only on the Feature Store snapshot + strategy config.

### 2.2 Runtime services

| Service | Responsibility |
|---|---|
| `api` | Versioned REST. No prediction loop. |
| `worker` | Prediction cycles, validation jobs, rolling stats, qualification. |
| `postgres` | System of record. |
| `pgadmin` (optional) | Local inspection. |

Scheduling lives in the worker (APScheduler or a simple async loop driven by config). FastAPI does not own cron.

### 2.3 Processing pipeline

```
Market Provider
    ↓
Market Data Service
    ↓
Data Normalizer
    ↓
Coin Selector                    ← independent service, not embedded in decision
    ↓
Feature Extraction Pipeline      ← Module Registry executes enabled modules
    ↓
Feature Store                    ← persisted feature_sets + per-module rows
    ↓
Decision Engine                  ← features in, prediction out. No indicator math.
    ↓
Prediction Store
    ↓
Validation Engine                ← later, when horizon elapses
    ↓
Rolling Statistics Engine
    ↓
Qualified Coin Generator
    ↓
REST API                         ← reads stores; does not mutate the cycle
```

### 2.4 Core contracts (Phase 1 shapes)

**MarketSnapshot** (normalizer output)

- `coin_id`, `symbol`, `venue`, `timeframe`, `as_of`
- OHLCV window, optional book summary, optional derivatives summary
- `raw_payload_ref` (provider payload stored or hashed)

**FeatureResult** (every module)

```text
module_key: str
module_version: str
coin_id: UUID
snapshot_id: UUID
features: dict[str, float | str | bool | None]
confidence: float | None          # module-local, 0-1
direction_hint: UP | DOWN | NEUTRAL | NONE
rationale: str | None
extras: dict                      # unstructured but versioned
```

Modules must not import each other. If two modules need the same RSI, either:

- both read raw OHLCV and compute independently (simple, Phase 1), or
- a future shared *primitive library* (not a module-to-module call) is introduced.

**Prediction** (Decision Engine output)

- direction, horizon, magnitude (optional), confidence
- engine_version, strategy_name, model_name, feature_version, config_version
- per-module contribution rows written in the same transaction

### 2.5 Decision Engine (renamed from Prediction Engine)

Phase 1 strategy: **weighted scoring rule engine**.

- Input: feature set for one coin + module weights/priorities from config.
- Output: direction, confidence, score breakdown.
- Forbidden: calling Binance, computing indicators, reading other modules’ source.

Swap path without refactor:

| Strategy name | When |
|---|---|
| `rules.weighted_v1` | Phase 1 |
| `ml.sklearn_v1` | later, same Feature Store |
| `llm.reasoner_v1` | later, top-N only |
| `vision.pattern_v1` | later |
| `ensemble.hybrid_v1` | later |

The engine is selected by `system_configuration` + experiment metadata, not by if/else scattered in the worker.

### 2.6 Coin selection (independent)

`CoinSelector` is a port with implementations:

- Phase 1: configured universe + Binance USDT-M / spot liquidity filter
- Later: CoinMarketCap, trending, news-driven, internal ranking

The prediction pipeline receives an already-selected coin list. It does not scrape “what to analyze” from inside a module.

### 2.7 Market provider abstraction

```text
MarketProvider
  list_instruments()
  fetch_ohlcv(symbol, timeframe, limit)
  fetch_ticker(symbol)                  # optional
  fetch_order_book(symbol, depth)       # optional
  fetch_derivatives_metrics(symbol)     # optional
```

Phase 1 implementation: `BinanceMarketProvider`.  
Future: Bybit, OKX, Hyperliquid. Changing provider must not change domain or modules that consume normalized snapshots.

### 2.8 Validation and reliability

When a prediction’s horizon elapses, Validation Engine records:

- predicted direction vs actual direction
- magnitude error (predicted move vs realized move)
- confidence and whether it was calibrated (bucketed reliability)
- market regime at prediction time and at validation time
- validation timestamp

Rolling Statistics Engine aggregates **from raw validation + module contribution rows**, never as the only stored truth.

Qualified Coin Generator applies configurable gates (sample size, hit rate, calibration error, recent form, regime fit) and writes `qualified_coins`.

### 2.9 API surface (resource-oriented, versioned)

Base: `/api/v1`

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/coins` | universe |
| GET | `/snapshots` | latest normalized market data |
| GET | `/features` | feature sets |
| GET | `/predictions` | predictions |
| GET | `/predictions/{id}` | prediction + module contributions |
| GET | `/validations` | outcome rows |
| GET | `/scores` | rolling scores |
| GET | `/qualified-coins` | current qualified set |
| GET | `/modules` | registry view |
| GET | `/config` | non-secret configuration |
| POST | `/admin/cycles` | optional manual trigger (dev) |

No execute / approve / order routes.

---

## 3. Technology stack

| Concern | Choice |
|---|---|
| Language | Python 3.12 |
| API | FastAPI |
| DB | PostgreSQL 16 |
| ORM / migrations | SQLAlchemy 2.x + Alembic |
| Worker scheduling | APScheduler or asyncio loop in worker process |
| Config | YAML + env overrides (pydantic-settings) |
| Containers | Docker Compose: api, worker, postgres, optional pgadmin |
| Tests | pytest |

Python is the long-term ecosystem for ML, LLMs, vision, and stats. That is the reason for the stack, not a rewrite of the JS bot.

---

## 4. Phase 1 module set (enabled by config)

Implemented as feature modules only:

- `trend`
- `momentum`
- `volatility`
- `volume`
- `rsi`
- `macd`
- `bollinger`
- `atr`

Registered but disabled until a later phase:

- support_resistance, news_sentiment, chart_pattern, vision_ai, llm_reasoning, order_book, funding_rate, liquidation

---

## 5. Approval gate

Implementation starts only after this package is approved:

1. Architecture (this file)
2. Folder structure
3. Dependency graph
4. Database schema
5. Docker architecture
6. Module discovery / future AI integration
7. Experiment tracking

No FastAPI app, no worker loop, no Alembic run against a real environment until that approval.
