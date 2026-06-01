from __future__ import annotations

import json
import uuid
from datetime import datetime

from backend.app.db import Database
from backend.app.services.strategy_service import (
    DEFAULT_STRATEGY_CONFIG,
    SYSTEM_PRESETS,
    _config_hash,
    _strategy_summary,
    insert_strategy_versions,
    normalize_strategy_config,
)


SCHEMA_VERSION = 14


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
    CREATE TABLE IF NOT EXISTS tushare_daily_basic (
        code TEXT,
        trade_date DATE,
        close DOUBLE,
        turnover_rate DOUBLE,
        turnover_rate_f DOUBLE,
        volume_ratio DOUBLE,
        pe DOUBLE,
        pe_ttm DOUBLE,
        pb DOUBLE,
        ps DOUBLE,
        ps_ttm DOUBLE,
        dv_ratio DOUBLE,
        dv_ttm DOUBLE,
        total_share DOUBLE,
        float_share DOUBLE,
        free_share DOUBLE,
        total_mv DOUBLE,
        circ_mv DOUBLE,
        source TEXT,
        updated_at TIMESTAMP,
        PRIMARY KEY (code, trade_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tushare_stk_factor (
        code TEXT,
        trade_date DATE,
        macd DOUBLE,
        kdj_k DOUBLE,
        kdj_d DOUBLE,
        kdj_j DOUBLE,
        rsi_6 DOUBLE,
        rsi_12 DOUBLE,
        rsi_24 DOUBLE,
        boll_upper DOUBLE,
        boll_mid DOUBLE,
        boll_lower DOUBLE,
        cci DOUBLE,
        source TEXT,
        updated_at TIMESTAMP,
        PRIMARY KEY (code, trade_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tushare_moneyflow (
        code TEXT,
        trade_date DATE,
        buy_sm_amount DOUBLE,
        sell_sm_amount DOUBLE,
        buy_md_amount DOUBLE,
        sell_md_amount DOUBLE,
        buy_lg_amount DOUBLE,
        sell_lg_amount DOUBLE,
        buy_elg_amount DOUBLE,
        sell_elg_amount DOUBLE,
        net_mf_amount DOUBLE,
        main_net_amount DOUBLE,
        source TEXT,
        updated_at TIMESTAMP,
        PRIMARY KEY (code, trade_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tushare_limit_list_d (
        code TEXT,
        trade_date DATE,
        name TEXT,
        close DOUBLE,
        pct_chg DOUBLE,
        limit_type TEXT,
        up_stat TEXT,
        fd_amount DOUBLE,
        first_time TEXT,
        last_time TEXT,
        open_times INTEGER,
        source TEXT,
        updated_at TIMESTAMP,
        PRIMARY KEY (code, trade_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tushare_cyq_perf (
        code TEXT,
        trade_date DATE,
        his_low DOUBLE,
        his_high DOUBLE,
        cost_5pct DOUBLE,
        cost_15pct DOUBLE,
        cost_50pct DOUBLE,
        cost_85pct DOUBLE,
        cost_95pct DOUBLE,
        weight_avg DOUBLE,
        winner_rate DOUBLE,
        source TEXT,
        updated_at TIMESTAMP,
        PRIMARY KEY (code, trade_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tushare_cyq_chips (
        code TEXT,
        trade_date DATE,
        price DOUBLE,
        percent DOUBLE,
        source TEXT,
        updated_at TIMESTAMP,
        PRIMARY KEY (code, trade_date, price)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tushare_ths_member (
        code TEXT,
        name TEXT,
        con_code TEXT,
        con_name TEXT,
        weight DOUBLE,
        in_date DATE,
        out_date DATE,
        is_new TEXT,
        source TEXT,
        updated_at TIMESTAMP,
        PRIMARY KEY (code, con_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tushare_top_list (
        code TEXT,
        trade_date DATE,
        name TEXT,
        close DOUBLE,
        pct_change DOUBLE,
        turnover_rate DOUBLE,
        amount DOUBLE,
        l_sell DOUBLE,
        l_buy DOUBLE,
        l_amount DOUBLE,
        net_amount DOUBLE,
        net_rate DOUBLE,
        amount_rate DOUBLE,
        float_values DOUBLE,
        reason TEXT,
        source TEXT,
        updated_at TIMESTAMP,
        PRIMARY KEY (code, trade_date, reason)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tushare_top_inst (
        code TEXT,
        trade_date DATE,
        exalter TEXT,
        buy DOUBLE,
        buy_rate DOUBLE,
        sell DOUBLE,
        sell_rate DOUBLE,
        net_buy DOUBLE,
        source TEXT,
        updated_at TIMESTAMP,
        PRIMARY KEY (code, trade_date, exalter)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tushare_hm_detail (
        code TEXT,
        trade_date DATE,
        name TEXT,
        hm_name TEXT,
        buy_amount DOUBLE,
        sell_amount DOUBLE,
        net_amount DOUBLE,
        source TEXT,
        updated_at TIMESTAMP,
        PRIMARY KEY (code, trade_date, hm_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tushare_index_daily (
        index_code TEXT,
        trade_date DATE,
        open DOUBLE,
        high DOUBLE,
        low DOUBLE,
        close DOUBLE,
        pre_close DOUBLE,
        change DOUBLE,
        pct_chg DOUBLE,
        volume DOUBLE,
        amount DOUBLE,
        source TEXT,
        updated_at TIMESTAMP,
        PRIMARY KEY (index_code, trade_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS market_environment (
        date DATE PRIMARY KEY,
        trend_score DOUBLE,
        risk_level TEXT,
        index_score DOUBLE,
        breadth_score DOUBLE,
        turnover_score DOUBLE,
        limit_score DOUBLE,
        up_count INTEGER,
        down_count INTEGER,
        flat_count INTEGER,
        limit_up_count INTEGER,
        limit_down_count INTEGER,
        strong_count INTEGER,
        weak_count INTEGER,
        total_amount DOUBLE,
        source TEXT,
        summary_json TEXT,
        updated_at TIMESTAMP
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
        updated_at TIMESTAMP,
        deleted_at TIMESTAMP
    )
    """,
    """
    ALTER TABLE strategy_presets ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_versions (
        id TEXT PRIMARY KEY,
        preset_id TEXT,
        strategy_name TEXT,
        version_number INTEGER,
        config_hash TEXT,
        config_json TEXT,
        summary TEXT,
        created_at TIMESTAMP,
        UNIQUE (preset_id, version_number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS signal_modes (
        id TEXT PRIMARY KEY,
        name TEXT,
        mode_json TEXT,
        sort_order INTEGER,
        created_at TIMESTAMP,
        updated_at TIMESTAMP,
        deleted_at TIMESTAMP
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
    ALTER TABLE analysis_runs ADD COLUMN IF NOT EXISTS task_id TEXT
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
    CREATE TABLE IF NOT EXISTS candidate_ai_summaries (
        run_id TEXT,
        code TEXT,
        status TEXT,
        task_id TEXT,
        input_hash TEXT,
        prompt_version TEXT,
        evidence_json TEXT,
        summary_json TEXT,
        llm_model TEXT,
        fallback_reason TEXT,
        error_message TEXT,
        requested_at TIMESTAMP,
        generated_at TIMESTAMP,
        updated_at TIMESTAMP,
        PRIMARY KEY (run_id, code)
    )
    """,
    """
    ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS status TEXT
    """,
    """
    ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS task_id TEXT
    """,
    """
    ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS input_hash TEXT
    """,
    """
    ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS prompt_version TEXT
    """,
    """
    ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS evidence_json TEXT
    """,
    """
    ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS fallback_reason TEXT
    """,
    """
    ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS error_message TEXT
    """,
    """
    ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS requested_at TIMESTAMP
    """,
    """
    ALTER TABLE candidate_ai_summaries ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP
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
        source_summary TEXT,
        note TEXT,
        review_status TEXT,
        name TEXT,
        status TEXT,
        created_at TIMESTAMP,
        updated_at TIMESTAMP
    )
    """,
    """
    ALTER TABLE watchlist_batches ADD COLUMN IF NOT EXISTS source_summary TEXT
    """,
    """
    ALTER TABLE watchlist_batches ADD COLUMN IF NOT EXISTS note TEXT
    """,
    """
    ALTER TABLE watchlist_batches ADD COLUMN IF NOT EXISTS review_status TEXT
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
        note TEXT,
        review_status TEXT,
        reasons_json TEXT,
        metrics_json TEXT,
        created_at TIMESTAMP,
        updated_at TIMESTAMP,
        PRIMARY KEY (batch_id, code)
    )
    """,
    """
    ALTER TABLE watchlist_items ADD COLUMN IF NOT EXISTS note TEXT
    """,
    """
    ALTER TABLE watchlist_items ADD COLUMN IF NOT EXISTS review_status TEXT
    """,
    """
    CREATE TABLE IF NOT EXISTS news_articles (
        source_id TEXT,
        source TEXT,
        category TEXT,
        title TEXT,
        url TEXT,
        excerpt TEXT,
        published_at TIMESTAMP,
        fetched_at TIMESTAMP,
        PRIMARY KEY (source_id, url)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_briefs (
        id TEXT PRIMARY KEY,
        brief_date DATE,
        status TEXT,
        hero_headline TEXT,
        daily_overview TEXT,
        tech_briefs_json TEXT,
        finance_briefs_json TEXT,
        politics_briefs_json TEXT,
        editor_note TEXT,
        keywords_json TEXT,
        article_count INTEGER,
        source_count INTEGER,
        llm_model TEXT,
        generated_at TIMESTAMP,
        error_message TEXT,
        payload_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS update_checkpoints (
      id TEXT PRIMARY KEY,
      task_id TEXT,
      job_id TEXT,
      capability TEXT,
      target_date DATE,
      batch_key TEXT,
      status TEXT,
      rows_written INTEGER,
      started_at TIMESTAMP,
      finished_at TIMESTAMP,
      error_message TEXT,
      payload_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS market_sector_daily (
      sector_code TEXT,
      sector_name TEXT,
      sector_type TEXT,
      trade_date DATE,
      pct_chg DOUBLE,
      amount DOUBLE,
      net_amount DOUBLE,
      company_count INTEGER,
      member_count INTEGER,
      limit_up_count INTEGER,
      limit_up_count_status TEXT,
      strong_count INTEGER,
      strong_count_status TEXT,
      limit_data_date DATE,
      quote_data_date DATE,
      leader_code TEXT,
      leader_name TEXT,
      leader_pct_chg DOUBLE,
      heat_score DOUBLE,
      source TEXT,
      updated_at TIMESTAMP,
      PRIMARY KEY (sector_code, sector_type, trade_date)
    )
    """,
    """
    ALTER TABLE market_sector_daily ADD COLUMN IF NOT EXISTS limit_up_count_status TEXT
    """,
    """
    ALTER TABLE market_sector_daily ADD COLUMN IF NOT EXISTS strong_count_status TEXT
    """,
    """
    ALTER TABLE market_sector_daily ADD COLUMN IF NOT EXISTS leader_pct_chg DOUBLE
    """,
    """
    ALTER TABLE market_sector_daily ADD COLUMN IF NOT EXISTS member_count INTEGER
    """,
    """
    ALTER TABLE market_sector_daily ADD COLUMN IF NOT EXISTS limit_data_date DATE
    """,
    """
    ALTER TABLE market_sector_daily ADD COLUMN IF NOT EXISTS quote_data_date DATE
    """,
    """
    CREATE TABLE IF NOT EXISTS factor_values (
      code TEXT,
      trade_date DATE,
      factor_id TEXT,
      value DOUBLE,
      source TEXT,
      updated_at TIMESTAMP,
      PRIMARY KEY (code, trade_date, factor_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS factor_definitions (
      factor_id TEXT PRIMARY KEY,
      name TEXT,
      category TEXT,
      formula TEXT,
      direction TEXT,
      frequency TEXT,
      enabled BOOLEAN,
      created_at TIMESTAMP,
      updated_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS watchlist_hypotheses (
      id TEXT PRIMARY KEY,
      batch_id TEXT,
      code TEXT,
      source_type TEXT,
      source_id TEXT,
      hypothesis TEXT,
      invalidation_rule TEXT,
      entry_date DATE,
      entry_price DOUBLE,
      review_status TEXT,
      trigger_rules_json TEXT,
      tags_json TEXT,
      created_at TIMESTAMP,
      updated_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS portfolio_backtest_runs (
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
    CREATE TABLE IF NOT EXISTS portfolio_backtest_trades (
      run_id TEXT,
      trade_id TEXT,
      code TEXT,
      name TEXT,
      entry_date DATE,
      entry_price DOUBLE,
      exit_date DATE,
      exit_price DOUBLE,
      shares DOUBLE,
      weight DOUBLE,
      return_pct DOUBLE,
      exit_reason TEXT,
      payload_json TEXT,
      PRIMARY KEY (run_id, trade_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS portfolio_backtest_equity (
      run_id TEXT,
      trade_date DATE,
      equity DOUBLE,
      cash DOUBLE,
      position_value DOUBLE,
      drawdown DOUBLE,
      PRIMARY KEY (run_id, trade_date)
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
    backfill_strategy_versions(db)


def seed_strategy_presets(db: Database) -> None:
    now = datetime.utcnow()
    existing = db.query("SELECT id FROM strategy_presets WHERE deleted_at IS NULL")
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
                "deleted_at": None,
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
                SET name = ?, config_json = ?, is_system = TRUE, deleted_at = NULL, updated_at = ?
                WHERE id = ? AND is_system = TRUE
                """,
                [row["name"], row["config_json"], now, row["id"]],
                write=True,
            )
        else:
            db.upsert("strategy_presets", [row], ["id"])
    if not db.scalar("SELECT COUNT(*) FROM strategy_presets WHERE is_default = TRUE AND deleted_at IS NULL"):
        db.execute(
            "UPDATE strategy_presets SET is_default = TRUE, deleted_at = NULL WHERE id = ?",
            [SYSTEM_PRESETS[0]["id"]],
            write=True,
        )


def backfill_strategy_versions(db: Database) -> None:
    rows = db.query(
        """
        SELECT p.id, p.name, p.config_json, p.updated_at
        FROM strategy_presets p
        LEFT JOIN strategy_versions v ON v.preset_id = p.id
        WHERE p.is_system = FALSE
          AND p.deleted_at IS NULL
          AND v.id IS NULL
        """
    )
    if not rows:
        return
    version_rows = []
    for row in rows:
        config = normalize_strategy_config(json.loads(row["config_json"] or "{}"))
        version_rows.append(
            {
                "id": f"version-{uuid.uuid4().hex[:12]}",
                "preset_id": row["id"],
                "strategy_name": row["name"] or "未命名策略",
                "version_number": 1,
                "config_hash": _config_hash(config),
                "config_json": json.dumps(config, ensure_ascii=False),
                "summary": _strategy_summary(config),
                "created_at": row.get("updated_at") or datetime.utcnow(),
            }
        )
    insert_strategy_versions(db, version_rows)
