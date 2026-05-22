from __future__ import annotations

import json
from datetime import datetime

from backend.app.db import Database
from backend.app.services.strategy_service import DEFAULT_STRATEGY_CONFIG, SYSTEM_PRESETS


SCHEMA_VERSION = 6


MIGRATIONS = [
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stock_basic (
        code TEXT PRIMARY KEY,
        name TEXT,
        exchange TEXT,
        list_date DATE,
        source TEXT,
        is_st BOOLEAN DEFAULT FALSE,
        suspended BOOLEAN DEFAULT FALSE,
        updated_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS historical_bars (
        code TEXT,
        date DATE,
        open DOUBLE,
        high DOUBLE,
        low DOUBLE,
        close DOUBLE,
        prev_close DOUBLE,
        volume DOUBLE,
        amount DOUBLE,
        turn DOUBLE,
        pct_chg DOUBLE,
        tradestatus TEXT,
        is_st BOOLEAN,
        source TEXT,
        updated_at TIMESTAMP,
        PRIMARY KEY (code, date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_snapshots (
        code TEXT,
        date DATE,
        name TEXT,
        latest_price DOUBLE,
        pct_chg DOUBLE,
        high DOUBLE,
        low DOUBLE,
        volume DOUBLE,
        amount DOUBLE,
        turnover_rate DOUBLE,
        float_market_value DOUBLE,
        source TEXT,
        updated_at TIMESTAMP,
        PRIMARY KEY (code, date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS float_market_values (
        code TEXT,
        date DATE,
        float_shares DOUBLE,
        float_market_value DOUBLE,
        source TEXT,
        updated_at TIMESTAMP,
        PRIMARY KEY (code, date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_status (
        source TEXT,
        capability TEXT,
        status TEXT,
        last_checked TIMESTAMP,
        last_success TIMESTAMP,
        last_failure TIMESTAMP,
        failure_reason TEXT,
        ttl_until TIMESTAMP,
        payload_json TEXT,
        PRIMARY KEY (source, capability)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS data_capabilities (
        capability TEXT PRIMARY KEY,
        actual_sources TEXT,
        fallback_sources TEXT,
        coverage_count INTEGER,
        missing_count INTEGER,
        latest_update TIMESTAMP,
        last_failure_reason TEXT,
        uses_cache BOOLEAN,
        can_backfill BOOLEAN,
        participates_in_analysis BOOLEAN,
        updated_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_presets (
        id TEXT PRIMARY KEY,
        name TEXT,
        config_json TEXT,
        is_system BOOLEAN,
        is_default BOOLEAN,
        created_at TIMESTAMP,
        updated_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS task_runs (
        id TEXT PRIMARY KEY,
        kind TEXT,
        status TEXT,
        stage TEXT,
        source TEXT,
        current_stock TEXT,
        total INTEGER,
        processed INTEGER,
        success INTEGER,
        failed INTEGER,
        skipped INTEGER,
        warning TEXT,
        summary_json TEXT,
        payload_json TEXT,
        queue_order BIGINT,
        cancel_requested BOOLEAN DEFAULT FALSE,
        started_at TIMESTAMP,
        updated_at TIMESTAMP,
        finished_at TIMESTAMP,
        error_message TEXT
    )
    """,
    """
    ALTER TABLE task_runs ADD COLUMN IF NOT EXISTS payload_json TEXT
    """,
    """
    ALTER TABLE task_runs ADD COLUMN IF NOT EXISTS queue_order BIGINT
    """,
    """
    CREATE TABLE IF NOT EXISTS analysis_runs (
        id TEXT PRIMARY KEY,
        status TEXT,
        started_at TIMESTAMP,
        finished_at TIMESTAMP,
        config_json TEXT,
        summary_json TEXT,
        error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS funnel_stats (
        run_id TEXT,
        order_index INTEGER,
        step_name TEXT,
        before_count INTEGER,
        after_count INTEGER,
        removed_count INTEGER,
        note TEXT,
        PRIMARY KEY (run_id, order_index)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidate_results (
        run_id TEXT,
        rank INTEGER,
        code TEXT,
        name TEXT,
        latest_price DOUBLE,
        pct_chg DOUBLE,
        amount DOUBLE,
        volume DOUBLE,
        turnover_rate DOUBLE,
        amplitude DOUBLE,
        rps20 DOUBLE,
        rps60 DOUBLE,
        rps120 DOUBLE,
        ma_short DOUBLE,
        ma_long DOUBLE,
        float_market_value DOUBLE,
        signal_type TEXT,
        signal_score DOUBLE,
        data_sources TEXT,
        reasons_json TEXT,
        chart_url TEXT,
        metrics_json TEXT,
        created_at TIMESTAMP,
        PRIMARY KEY (run_id, code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS warnings (
        id TEXT PRIMARY KEY,
        scope TEXT,
        level TEXT,
        message TEXT,
        detail TEXT,
        created_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_runs (
        id TEXT PRIMARY KEY,
        status TEXT,
        started_at TIMESTAMP,
        finished_at TIMESTAMP,
        config_json TEXT,
        summary_json TEXT,
        error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS backtest_signals (
        run_id TEXT,
        as_of_date DATE,
        rank INTEGER,
        code TEXT,
        name TEXT,
        latest_price DOUBLE,
        signal_type TEXT,
        signal_score DOUBLE,
        reasons_json TEXT,
        metrics_json TEXT,
        entry_date DATE,
        entry_price DOUBLE,
        return_5d DOUBLE,
        return_10d DOUBLE,
        return_20d DOUBLE,
        max_return_10d DOUBLE,
        max_drawdown_10d DOUBLE,
        hit_5pct_10d BOOLEAN,
        hit_8pct_10d BOOLEAN,
        hit_stop_5pct_10d BOOLEAN,
        created_at TIMESTAMP,
        PRIMARY KEY (run_id, as_of_date, code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS intraday_snapshots (
        code TEXT,
        trade_date DATE,
        sample_at TIMESTAMP,
        name TEXT,
        latest_price DOUBLE,
        pct_chg DOUBLE,
        high DOUBLE,
        low DOUBLE,
        volume DOUBLE,
        amount DOUBLE,
        source TEXT,
        created_at TIMESTAMP,
        PRIMARY KEY (code, sample_at)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS intraday_radar_config (
        id TEXT PRIMARY KEY,
        config_json TEXT,
        updated_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS intraday_radar_candidates (
        sample_at TIMESTAMP,
        trade_date DATE,
        rank INTEGER,
        code TEXT,
        name TEXT,
        status TEXT,
        radar_score DOUBLE,
        latest_price DOUBLE,
        pct_chg DOUBLE,
        amount DOUBLE,
        volume DOUBLE,
        distance_to_upper DOUBLE,
        breakout_clearance DOUBLE,
        amount_delta DOUBLE,
        volume_delta DOUBLE,
        amount_ratio DOUBLE,
        price_change DOUBLE,
        source TEXT,
        reasons_json TEXT,
        metrics_json TEXT,
        created_at TIMESTAMP,
        PRIMARY KEY (sample_at, code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS intraday_radar_rankings (
        sample_at TIMESTAMP,
        radar_mode TEXT,
        trade_date DATE,
        rank INTEGER,
        code TEXT,
        name TEXT,
        status TEXT,
        radar_score DOUBLE,
        latest_price DOUBLE,
        pct_chg DOUBLE,
        amount DOUBLE,
        volume DOUBLE,
        distance_to_upper DOUBLE,
        breakout_clearance DOUBLE,
        amount_delta DOUBLE,
        volume_delta DOUBLE,
        amount_ratio DOUBLE,
        price_change DOUBLE,
        source TEXT,
        reasons_json TEXT,
        metrics_json TEXT,
        created_at TIMESTAMP,
        PRIMARY KEY (sample_at, radar_mode, code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist_batches (
        id TEXT PRIMARY KEY,
        batch_date DATE,
        source_type TEXT,
        source_label TEXT,
        source_ref TEXT,
        name TEXT,
        status TEXT,
        created_at TIMESTAMP,
        updated_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist_items (
        batch_id TEXT,
        code TEXT,
        name TEXT,
        entry_date DATE,
        entry_price DOUBLE,
        source_type TEXT,
        source_label TEXT,
        source_ref TEXT,
        signal_score DOUBLE,
        signal_type TEXT,
        chart_url TEXT,
        reasons_json TEXT,
        metrics_json TEXT,
        created_at TIMESTAMP,
        updated_at TIMESTAMP,
        PRIMARY KEY (batch_id, code)
    )
    """,
]


def migrate(db: Database) -> None:
    for sql in MIGRATIONS:
        db.execute(sql, write=True)
    db.upsert(
        "schema_migrations",
        [{"version": SCHEMA_VERSION, "applied_at": datetime.utcnow()}],
        ["version"],
    )
    seed_strategy_presets(db)


def seed_strategy_presets(db: Database) -> None:
    now = datetime.utcnow()
    existing = db.query("SELECT id FROM strategy_presets")
    existing_ids = {row["id"] for row in existing}
    rows = []
    for preset in SYSTEM_PRESETS:
        rows.append(
            {
                "id": preset["id"],
                "name": preset["name"],
                "config_json": json.dumps(preset["config"], ensure_ascii=False),
                "is_system": True,
                "is_default": preset.get("is_default", False),
                "created_at": now,
                "updated_at": now,
            }
        )
    if not existing_ids:
        db.upsert("strategy_presets", rows, ["id"])
        return
    for row in rows:
        if row["id"] in existing_ids:
            db.execute(
                """
                UPDATE strategy_presets
                SET name = ?, config_json = ?, is_system = TRUE, updated_at = ?
                WHERE id = ? AND is_system = TRUE
                """,
                [row["name"], row["config_json"], now, row["id"]],
                write=True,
            )
        else:
            db.upsert("strategy_presets", [row], ["id"])
    if not db.scalar("SELECT COUNT(*) FROM strategy_presets WHERE is_default = TRUE"):
        db.execute(
            "UPDATE strategy_presets SET is_default = TRUE WHERE id = ?",
            [SYSTEM_PRESETS[0]["id"]],
            write=True,
        )
