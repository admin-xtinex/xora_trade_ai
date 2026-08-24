# XORA Trading Engine V2 — Architecture & Migration Specification

**Status:** DESIGN for review (no engine code changed yet). **Constraint:** this is a
live real-money engine — V2 ships behind a flag, in **shadow mode first** (logs what
it *would* trade, compared against V1, before it is ever allowed to execute).

> This document fulfils the spec's first implementation requirement: *review the
> existing engine, identify reuse, and produce a migration architecture BEFORE code.*

---

## 1. Core reframe (what actually changes)

**Today (V1):** each symbol is independently evaluated — "can I enter this coin *now*?"
`evaluateEntry()` runs S/R → confirmation → R:R → indicators, returns PASS/REJECT, and
the scanner submits passers in confidence order. Discovery, prediction, and ranking are
implicit and per-symbol.

**V2:** a **market-wide, structure-first prediction and ranking layer** sits *in front*
of the (largely reused) entry validator. The engine first asks **"across 50-60 symbols,
where is price most likely to react, and how strongly?"**, builds a ranked opportunity
table, and only then validates the top candidates with the existing geometry checks.
Indicators are demoted to **verification only**.

The redesign is therefore **additive and re-sequencing**, not a rewrite. The proven
geometry (S/R location, confirmation candle, R:R/fee floor, SL/TP construction) is
preserved; what's new is *multi-zone structure*, *directional probability prediction*,
*market-wide ranking*, and *indicators-as-veto*.

---

## 2. Current-engine review — reuse map (mandated)

| Existing component (file) | V1 role | V2 disposition |
|---|---|---|
| `market_structure.js` — `findSwingPivots`, `clusterLevels`, `detectStructure`, `findConfirmedHigherLow/LowerHigh`, `getBid/AskLiquidityNear` | swing/zone primitives | **REUSE as the foundation** of `structure_engine.js` + `dynamic_zone_tracker.js` |
| `engines/entryEngine.js` — `evaluateDirection` (S/R→confirmation→R:R→geometry), `checkRiskReward` | per-symbol entry decision | **REUSE the geometry/validation half**; the *discovery/direction-choice* half is superseded by prediction+ranking. Becomes the validator inside `entry_engine_v2.js` |
| `engines/breakoutEngine.js` — `evaluateBreakout`, `deriveBreakoutContext` | breakout-pullback trade | **REUSE** — already regime + weakened-resistance + retest aware, exactly the spec's breakout rules |
| `analyzeMomentum()` (server.js) | indicator scorer → `breakoutProbability`, order-flow, pressure | **DEMOTE to `indicator_verification_engine.js`** — its scalars become veto/confidence inputs, never trade generators |
| `analysis/execution_quality.js` — `scoreCandidate`, `rankCandidates`, `RANKING_WEIGHTS` | composite candidate ranker (built, then reverted from use by `5f9aaa1`) | **REUSE + EXTEND as `opportunity_ranker.js`** — add structure/prediction/expectancy weights |
| `analysis/scanners.js` — `runScanners`, `weightedScore`, `scan*` (breakout_loading, momentum, smart_money, short_squeeze, breakdown_risk) | multi-scanner feature scoring | **REUSE as feature inputs** to prediction + ranking |
| `analysis/pulse_analysis.js` — `buildTimeframePredictions`, `buildAiConfidence`, `buildTradeZones` | timeframe bias/prediction helpers | **REUSE as inputs** to `market_prediction_engine.js` |
| multi-timeframe (`mtf` 1m/5m/15m), `classifyMarketStructure`, `detectMarketState`, `btcDrift1hPct` | market context | **REUSE** as prediction context (BTC/24h/regime) |
| **Execution & safety (PRESERVE UNCHANGED):** `/api/xora/approve`, position sizing (`position_sizing.js`, `portfolio_capital.js`), SL/TP placement, `runTradeMonitor` + exit engine, cooldowns (`recentCloses`, loss-streak), dedup guards, Binance integration, notifications, history, config #11, exit forensics | execution/monitoring/safety | **NO CHANGES** — V2 emits the same approval payload shape; everything downstream is untouched |

**Net:** ~70% of the machinery is reused. V2 introduces 4 genuinely new responsibilities
(multi-zone tracking, directional prediction, market-wide ranking, indicators-as-veto)
and re-wires the scan → decide flow.

---

## 3. V2 module architecture

```
                 ┌─────────────────────── SCAN LOOP (50-60 symbols) ──────────────────────┐
                 │                                                                          │
 klines+book ─▶ structure_engine.js ─▶ dynamic_zone_tracker.js ─▶ market_prediction_engine.js
 (per symbol)    (top 3-5 S + 3-5 R,     (evolves zones: HL/LH,      (15m & 1h bull/bear/neutral
                  strength-scored)         promote/weaken, absorb)     probability + reason)
                                                                              │
                                                                              ▼
                                                    indicator_verification_engine.js
                                                    (RSI/MACD/vol/book/OI/funding →
                                                     confirm / dampen / VETO the prediction)
                                                                              │
                                          ┌───────────────────────────────────┘
                                          ▼
                              opportunity_ranker.js  ──▶  market-wide Opportunity Table
                              (structure×prediction×RR×liquidity×expectancy → 0-100)
                                          │  (top N only)
                                          ▼
                              entry_engine_v2.js
                              (REUSES entryEngine geometry + breakoutEngine:
                               confirmation candle, SL=structure−ATR, TP=next zone,
                               R:R≥2 preferred, fee floor)
                                          │  (same approval payload as today)
                                          ▼
                    ══════ EXISTING EXECUTION (unchanged) ══════
                    /api/xora/approve → watcher → session → monitor/exit → history
                                          │
                                          ▼
                              learning_store (trade outcome + full decision context)
```

### 3.1 `structure_engine.js`
- Input: closed klines (multi-window: 50/100/200 candles), order book.
- Output: **top 3-5 support + 3-5 resistance zones**, each with:
  `price, strength(0-100), freshness, retests, rejectionCount, obLiquidity, swingSignificance, higherLowContribution, lowerHighContribution, demandQuality`.
- Built from `findSwingPivots` + `clusterLevels` + `getBid/AskLiquidityNear` (all existing),
  plus a new **zone-strength model** combining those features into a single 0-100 score.
- *Why:* the spec's #1 change is "multiple structural zones, not only the nearest." V1's
  `detectStructure` returns one current S/R; this generalises it to a ranked zone set.

### 3.2 `dynamic_zone_tracker.js`
- Maintains per-symbol zone state **across scans** (in-memory, bounded).
- Detects: new higher-lows / lower-highs → **promotes** them to primary; repeated tests →
  **weakens** a level and raises its breakout probability; buyer/seller **absorption**.
- Uses existing `findConfirmedHigherLow/LowerHigh` + absorption logic already in
  `analyzeMomentum` (sellerAbsorption/supportStrengthening/resistanceWeakening).
- *Why:* the spec requires S/R to *evolve* ("old support 100 → new higher low 104 becomes
  primary"). This is the stateful layer V1 lacks.

### 3.3 `market_prediction_engine.js` — the largest change
- Input: structure zones + zone evolution + market context (mtf bias, BTC drift, 24h trend,
  volume, order book, volatility) + optional funding/OI.
- Output, per symbol: **15m and 1h {bullProb, bearProb, neutralProb, reason}**.
- **Primary predictor = deterministic structural-probability model** (see §4 for why *not*
  an LLM per symbol). It converts "price sitting on a strong, holding, absorbing support
  with bullish mtf and weakening resistance above" into a calibrated bull probability,
  reusing `buildTimeframePredictions`/`buildAiConfidence` as seeds and calibrating against
  the learning store.
- **Optional LLM enrichment** only on the **top-N ranked** symbols (not all 50-60), via the
  existing Groq pool — additive reasoning/adjustment, rate-limit-safe.

### 3.4 `indicator_verification_engine.js`
- Input: the prediction + RSI, MACD, momentum, volume, order-book imbalance, funding, OI.
- Output: `verdict ∈ {CONFIRM, DAMPEN, VETO}` + confidence delta.
- **Hard rule enforced here:** indicators can only *confirm/dampen/veto* an existing
  structural prediction — they can **never originate** a trade. This is `analyzeMomentum`'s
  order-flow veto generalised and made the *only* role indicators play.

### 3.5 `opportunity_ranker.js`
- Input: all verified predictions across the scanned universe.
- Output: a **single market-wide Opportunity Table**, each row scored 0-100 from:
  structure quality, prediction confidence, R:R, zone strength, liquidity, trend quality,
  volatility fit, expected reward, expected loss, historical setup expectancy.
- Extends the existing `scoreCandidate`/`rankCandidates` with the new structure/prediction/
  expectancy terms. Only the **top K** rows (K = available trade slots) proceed.
- *Why:* "trade the best opportunity anywhere, not every setup." V1 submits every passer in
  confidence order; V2 competes them market-wide and takes only the best.

### 3.6 `entry_engine_v2.js`
- Consumes a top-ranked opportunity and produces the **execution payload** — reusing
  `entryEngine`'s confirmation-candle check, structural SL (`structuralAnchor − ATR`, never
  %), TP at next structural zone, and `checkRiskReward` (R:R ≥ 2 preferred, fee floor), and
  `breakoutEngine` for the breakout path. Emits the **identical `/api/xora/approve` body**
  used today → zero downstream changes.

### 3.7 Learning store (spec "Learning Engine")
- On every close, record: predicted direction/confidence, 15m/1h probabilities, zone
  strengths, prediction reason, indicator verdict, entry/exit, outcome, MFE/MAE.
- **Reuses the Exit-Forensics Phase-1 record** (already isolated in `forensic#…`) — extend
  its schema rather than build a second store. Feeds prediction calibration (§3.3).

---

## 4. Key design decision — the "AI prediction" (biggest risk)

The spec says the AI must output bull/bear/neutral probabilities for 15m/1h. **Doing this
with an LLM for all 50-60 symbols every scan tick is not viable** — it would reproduce the
2026-07-13 rate-limit/cadence incident (the Groq pool is already cooldown-managed and the
Binance market-data budget is the binding constraint at scale).

**Decision: a two-tier predictor.**
1. **Deterministic structural-probability model (primary, all symbols).** Calibrated,
   fast, testable, and — critically — *back-testable against the learning store* so its
   probabilities become honest (V1's `confidence` was famously uncalibrated). This is what
   the spec really needs: "given structure, the most probable reaction."
2. **LLM enrichment (optional, top-N only).** The existing Groq layer adds narrative reason
   + a bounded probability adjustment on the handful of symbols that already rank highest.

This satisfies "AI predicts likely reactions before trade decisions" while staying
production-safe. *Rationale:* prediction quality comes from **calibration against real
outcomes**, not from an LLM call per coin; the LLM adds explanation and edge-case judgement
where it's affordable.

---

## 5. Data availability & gaps (evidence-checked)

| Prediction input (spec) | Available today? | Plan |
|---|---|---|
| Market structure, S/R strength | ✅ (`detectStructure`, pivots, clusters) | reuse |
| BTC context, 24h trend, mtf regime | ✅ (`btcDrift1hPct`, `mtf`, `classifyMarketStructure`) | reuse; add **ETH** context (same mechanism) |
| Volume, order book, volatility, momentum | ✅ | reuse |
| **Funding rate** | ❌ not fetched | **addable** (Binance `/fapi/v1/premiumIndex`), but costs rate-limit budget → fetch only for **ranked top-N**, cached |
| **Open interest** | ❌ not fetched | **addable** (`/fapi/v1/openInterest`), same top-N/cached approach |
| **News / sentiment** | ❌ no source in system | **deferred** — needs an external feed; excluded from V1 of V2, flagged as a spec item that can't be met without new infra |

*Why top-N/cached for funding+OI:* fetching them for all 60 symbols every tick re-creates
the known rate-limit failure; they're only needed to *verify* the best candidates, so
fetch-on-rank keeps the cost bounded.

---

#