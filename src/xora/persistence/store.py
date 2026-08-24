from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text

from xora.domain.models import FeatureResult, MarketSnapshot
from xora.persistence.db import get_engine


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Store:
    def __init__(self) -> None:
        self.engine = get_engine()

    def upsert_coin(self, symbol: str, venue: str = "binance") -> UUID:
        base, quote = symbol[:-4], symbol[-4:]
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO coins (symbol, base_asset, quote_asset, venue)
                    VALUES (:symbol, :base, :quote, :venue)
                    ON CONFLICT (venue, symbol, instrument_type)
                    DO UPDATE SET updated_at = now()
                    RETURNING id
                    """
                ),
                {"symbol": symbol, "base": base, "quote": quote, "venue": venue},
            ).one()
            return row.id

    def insert_snapshot(self, coin_id: UUID, snapshot: MarketSnapshot, payload_hash: str) -> UUID:
        ohlcv = [
            {
                "time": c.time,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in snapshot.candles
        ]
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO market_snapshots
                        (coin_id, venue, timeframe, as_of, ohlcv, ticker, payload, payload_hash)
                    VALUES
                        (:coin_id, :venue, :timeframe, :as_of, CAST(:ohlcv AS jsonb),
                         CAST(:ticker AS jsonb), CAST(:payload AS jsonb), :payload_hash)
                    RETURNING id
                    """
                ),
                {
                    "coin_id": coin_id,
                    "venue": snapshot.venue,
                    "timeframe": snapshot.timeframe,
                    "as_of": snapshot.as_of,
                    "ohlcv": json.dumps(ohlcv),
                    "ticker": json.dumps(snapshot.ticker) if snapshot.ticker else None,
                    "payload": json.dumps({"symbol": snapshot.symbol}),
                    "payload_hash": payload_hash,
                },
            ).one()
            return row.id

    def insert_feature_set(
        self,
        coin_id: UUID,
        snapshot_id: UUID,
        feature_version: str,
        config_version: str,
        results: list[FeatureResult],
    ) -> UUID:
        with self.engine.begin() as conn:
            fs = conn.execute(
                text(
                    """
                    INSERT INTO feature_sets (coin_id, snapshot_id, feature_version, config_version)
                    VALUES (:coin_id, :snapshot_id, :feature_version, :config_version)
                    RETURNING id
                    """
                ),
                {
                    "coin_id": coin_id,
                    "snapshot_id": snapshot_id,
                    "feature_version": feature_version,
                    "config_version": config_version,
                },
            ).one()
            for result in results:
                conn.execute(
                    text(
                        """
                        INSERT INTO feature_set_items
                            (feature_set_id, module_name, module_version, features, confidence,
                             direction_hint, rationale, extras, error)
                        VALUES
                            (:feature_set_id, :module_name, :module_version, CAST(:features AS jsonb),
                             :confidence, :direction_hint, :rationale, CAST(:extras AS jsonb), :error)
                        """
                    ),
                    {
                        "feature_set_id": fs.id,
                        "module_name": result.module_key,
                        "module_version": result.module_version,
                        "features": json.dumps(result.features),
                        "confidence": result.confidence,
                        "direction_hint": result.direction_hint.value if result.direction_hint else None,
                        "rationale": result.rationale,
                        "extras": json.dumps(result.extras),
                        "error": result.error,
                    },
                )
            return fs.id

    def insert_prediction(self, payload: dict[str, Any], contributions: list[dict[str, Any]]) -> UUID:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    INSERT INTO predictions (
                        coin_id, feature_set_id, snapshot_id, direction, horizon, magnitude,
                        confidence, score, market_regime, engine_version, strategy_name,
                        model_name, feature_version, config_version, experiment_name,
                        predicted_at, horizon_at, metadata
                    ) VALUES (
                        :coin_id, :feature_set_id, :snapshot_id, :direction, :horizon, :magnitude,
                        :confidence, :score, :market_regime, :engine_version, :strategy_name,
                        :model_name, :feature_version, :config_version, :experiment_name,
                        :predicted_at, :horizon_at, CAST(:metadata AS jsonb)
                    ) RETURNING id
                    """
                ),
                payload,
            ).one()
            for item in contributions:
                conn.execute(
                    text(
                        """
                        INSERT INTO prediction_modules
                            (prediction_id, module_name, module_version, weight, confidence,
                             contribution, decision, raw_features)
                        VALUES
                            (:prediction_id, :module_name, :module_version, :weight, :confidence,
                             :contribution, :decision, CAST(:raw_features AS jsonb))
                        """
                    ),
                    {"prediction_id": row.id, **item},
                )
            return row.id

    def due_predictions(self) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT p.id, p.coin_id, p.snapshot_id, p.direction, p.magnitude, p.confidence,
                           p.market_regime, p.horizon_at, c.symbol, s.ohlcv
                    FROM predictions p
                    JOIN coins c ON c.id = p.coin_id
                    JOIN market_snapshots s ON s.id = p.snapshot_id
                    LEFT JOIN validations v ON v.prediction_id = p.id
                    WHERE v.id IS NULL AND p.horizon_at <= now()
                    ORDER BY p.horizon_at ASC
                    LIMIT 50
                    """
                )
            ).mappings().all()
            return [dict(r) for r in rows]

    def insert_validation(self, payload: dict[str, Any]) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO validations (
                        prediction_id, predicted_direction, actual_direction,
                        predicted_magnitude, actual_magnitude, magnitude_error,
                        confidence, calibration_bucket, market_regime, is_correct,
                        reference_price, realized_price, extras
                    ) VALUES (
                        :prediction_id, :predicted_direction, :actual_direction,
                        :predicted_magnitude, :actual_magnitude, :magnitude_error,
                        :confidence, :calibration_bucket, :market_regime, :is_correct,
                        :reference_price, :realized_price, CAST(:extras AS jsonb)
                    )
                    ON CONFLICT (prediction_id) DO NOTHING
                    """
                ),
                payload,
            )

    def refresh_rolling_scores(self, experiment_name: str, strategy_name: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO rolling_scores (
                        coin_id, window, experiment_name, strategy_name, sample_size,
                        hit_rate, avg_confidence, calibration_error, avg_magnitude_error, score
                    )
                    SELECT p.coin_id, 'all', p.experiment_name, p.strategy_name,
                           COUNT(*)::int,
                           AVG(CASE WHEN v.is_correct THEN 1.0 ELSE 0.0 END),
                           AVG(v.confidence),
                           ABS(AVG(CASE WHEN v.is_correct THEN 1.0 ELSE 0.0 END) - AVG(v.confidence)),
                           AVG(ABS(COALESCE(v.magnitude_error, 0))),
                           AVG(CASE WHEN v.is_correct THEN 1.0 ELSE 0.0 END)
                    FROM validations v
                    JOIN predictions p ON p.id = v.prediction_id
                    WHERE p.experiment_name = :experiment_name AND p.strategy_name = :strategy_name
                    GROUP BY p.coin_id, p.experiment_name, p.strategy_name
                    ON CONFLICT (coin_id, window, experiment_name, strategy_name)
                    DO UPDATE SET
                        sample_size = EXCLUDED.sample_size,
                        hit_rate = EXCLUDED.hit_rate,
                        avg_confidence = EXCLUDED.avg_confidence,
                        calibration_error = EXCLUDED.calibration_error,
                        avg_magnitude_error = EXCLUDED.avg_magnitude_error,
                        score = EXCLUDED.score,
                        computed_at = now()
                    """
                ),
                {"experiment_name": experiment_name, "strategy_name": strategy_name},
            )

    def replace_qualified(self, rows: list[dict[str, Any]], experiment_name: str, strategy_name: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE qualified_coins
                    SET is_current = FALSE
                    WHERE experiment_name = :experiment_name AND strategy_name = :strategy_name AND is_current
                    """
                ),
                {"experiment_name": experiment_name, "strategy_name": strategy_name},
            )
            for row in rows:
                conn.execute(
                    text(
                        """
                        INSERT INTO qualified_coins
                            (coin_id, experiment_name, strategy_name, reason, score, gates, is_current)
                        VALUES
                            (:coin_id, :experiment_name, :strategy_name, :reason, :score, CAST(:gates AS jsonb), TRUE)
                        """
                    ),
                    row,
                )

    def rolling_scores(self) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT r.*, c.symbol
                    FROM rolling_scores r
                    JOIN coins c ON c.id = r.coin_id
                    ORDER BY r.score DESC NULLS LAST
                    """
                )
            ).mappings().all()
            return [dict(x) for x in rows]

    def upsert_module(self, name: str, version: str, enabled: bool, weight: float, priority: int, configuration: dict[str, Any], checksum: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO module_registry (module_name, module_version, enabled, weight, priority, configuration, checksum)
                    VALUES (:name, :version, :enabled, :weight, :priority, CAST(:configuration AS jsonb), :checksum)
                    ON CONFLICT (module_name) DO UPDATE SET
                        module_version = EXCLUDED.module_version,
                        enabled = EXCLUDED.enabled,
                        weight = EXCLUDED.weight,
                        priority = EXCLUDED.priority,
                        configuration = EXCLUDED.configuration,
                        checksum = EXCLUDED.checksum,
                        updated_at = now()
                    """
                ),
                {
                    "name": name,
                    "version": version,
                    "enabled": enabled,
                    "weight": weight,
                    "priority": priority,
                    "configuration": json.dumps(configuration),
                    "checksum": checksum,
                },
            )

    def heartbeat(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO system_configuration (key, value)
                    VALUES ('worker_heartbeat', CAST(:value AS jsonb))
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
                    """
                ),
                {"value": json.dumps({"at": _now().isoformat()})},
            )

    def list_rows(self, table: str, limit: int = 50) -> list[dict[str, Any]]:
        allowed = {
            "coins": "SELECT * FROM coins ORDER BY symbol",
            "snapshots": "SELECT id, coin_id, venue, timeframe, as_of, payload_hash FROM market_snapshots ORDER BY as_of DESC LIMIT :limit",
            "features": "SELECT * FROM feature_sets ORDER BY created_at DESC LIMIT :limit",
            "predictions": """
                SELECT p.*, c.symbol
                FROM predictions p JOIN coins c ON c.id = p.coin_id
                ORDER BY p.predicted_at DESC LIMIT :limit
            "",
            "validations": "SELECT * FROM validations ORDER BY validated_at DESC LIMIT :limit",
            "modules": "SELECT * FROM module_registry ORDER BY priority, module_name",
            "qualified": """
                SELECT q.*, c.symbol
                FROM qualified_coins q JOIN coins c ON c.id = q.coin_id
                WHERE q.is_current
                ORDER BY q.score DESC
            "",
            "scores": """
                SELECT r.*, c.symbol
                FROM rolling_scores r JOIN coins c ON c.id = r.coin_id
                ORDER BY r.score DESC NULLS LAST
            "",
        }
        sql = allowed[table]
        with self.engine.begin() as conn:
            rows = conn.execute(text(sql), {"limit": limit}).mappings().all()
            out = []
            for row in rows:
                item = dict(row)
                for key, value in list(item.items()):
                    if hasattr(value, "hex"):
                        item[key] = str(value)
                    elif hasattr(value, "isoformat"):
                        item[key] = value.isoformat()
                out.append(item)
            return out

    def prediction_detail(self, prediction_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            pred = conn.execute(
                text(
                    """
                    SELECT p.*, c.symbol
                    FROM predictions p JOIN coins c ON c.id = p.coin_id
                    WHERE p.id = CAST(:id AS uuid)
                    """
                ),
                {"id": prediction_id},
            ).mappings().first()
            if not pred:
                return None
            mods = conn.execute(
                text("SELECT * FROM prediction_modules WHERE prediction_id = CAST(:id AS uuid)"),
                {"id": prediction_id},
            ).mappings().all()
            item = dict(pred)
            for key, value in list(item.items()):
                if hasattr(value, "hex"):
                    item[key] = str(value)
                elif hasattr(value, "isoformat"):
                    item[key] = value.isoformat()
            item["modules"] = []
            for mod in mods:
                row = dict(mod)
                for key, value in list(row.items()):
                    if hasattr(value, "hex"):
                        row[key] = str(value)
                item["modules"].append(row)
            return item
