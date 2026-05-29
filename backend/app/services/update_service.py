from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from backend.app.config import settings
from backend.app.db import Database
from backend.app.services.data_service import DataService
from backend.app.services.daily_brief_service import DailyBriefService
from backend.app.services.intraday_service import IntradayRadarService
from backend.app.services.market_utils import safe_float
from backend.app.services.strategy_service import normalize_strategy_config
from backend.app.sources.akshare_source import AkShareSource
from backend.app.sources.baostock_source import BaostockSource
from backend.app.sources.base import SourceGuard
from backend.app.sources.tushare_source import TushareEnrichmentSource, TushareRealtimeSource

CHINA_TZ = ZoneInfo("Asia/Shanghai")
HISTORY_CLOSE_HOUR = 16
logger = logging.getLogger(__name__)
TUSHARE_RATE_LIMIT_RETRY_DELAYS = (1.5, 3.0, 6.0)
TUSHARE_RATE_LIMITS_PER_MINUTE = {
    "realtime": 500,
    "daily_basic": 500,
    "stk_factor": 500,
    "moneyflow": 500,
    "cyq": 200,
    "top": 200,
    "ths": 200,
}
DEFAULT_DATA_DAG: List[Dict[str, Any]] = [
    {
        "id": "stock_basic",
        "label": "股票基础信息",
        "capability": "股票基础信息",
        "dependencies": [],
        "freshness_policy": "long_lived",
        "coverage_policy": {"denominator": "active_stock", "min_complete_ratio": 0.98},
        "request_policy": {"source": "baostock", "rate_limit_group": "baostock"},
    },
    {
        "id": "daily_snapshot",
        "label": "实时日线 / 当日快照",
        "capability": "当天行情快照",
        "dependencies": ["stock_basic"],
        "freshness_policy": "intraday",
        "coverage_policy": {"denominator": "active_stock", "min_complete_ratio": 0.95},
        "request_policy": {"source": "tushare", "rate_limit_group": "realtime"},
    },
    {
        "id": "history_qfq",
        "label": "历史前复权 K 线",
        "capability": "历史 K 线",
        "dependencies": ["daily_snapshot"],
        "freshness_policy": "daily",
        "coverage_policy": {"denominator": "active_stock", "min_complete_ratio": 0.95},
        "request_policy": {"source": "tushare", "rate_limit_group": "daily"},
    },
    {
        "id": "daily_basic",
        "label": "每日指标",
        "capability": "每日指标",
        "dependencies": ["history_qfq"],
        "freshness_policy": "daily",
        "coverage_policy": {"denominator": "active_stock", "min_complete_ratio": 0.95},
        "request_policy": {"source": "tushare", "rate_limit_group": "daily_basic"},
    },
    {
        "id": "stk_factor",
        "label": "技术因子",
        "capability": "技术因子",
        "dependencies": ["history_qfq"],
        "freshness_policy": "daily",
        "coverage_policy": {"denominator": "active_stock", "min_complete_ratio": 0.95},
        "request_policy": {"source": "tushare", "rate_limit_group": "stk_factor"},
    },
    {
        "id": "moneyflow",
        "label": "资金流向",
        "capability": "资金流向",
        "dependencies": ["history_qfq"],
        "freshness_policy": "daily",
        "coverage_policy": {"denominator": "active_stock", "min_complete_ratio": 0.9},
        "request_policy": {"source": "tushare", "rate_limit_group": "moneyflow"},
    },
    {
        "id": "limit_list_d",
        "label": "涨跌停事件",
        "capability": "涨跌停",
        "dependencies": ["history_qfq"],
        "freshness_policy": "event",
        "coverage_policy": {"denominator": "event", "min_rows": 1},
        "request_policy": {"source": "tushare", "rate_limit_group": "top"},
    },
    {
        "id": "cyq_perf",
        "label": "筹码表现",
        "capability": "筹码分布",
        "dependencies": ["history_qfq"],
        "freshness_policy": "daily",
        "coverage_policy": {"denominator": "active_stock", "min_complete_ratio": 0.8},
        "request_policy": {"source": "tushare", "rate_limit_group": "cyq", "batch_size": 200},
    },
    {
        "id": "cyq_chips",
        "label": "筹码价格分布",
        "capability": "筹码分布",
        "dependencies": ["history_qfq"],
        "freshness_policy": "daily",
        "coverage_policy": {"denominator": "active_stock", "min_complete_ratio": 0.8},
        "request_policy": {"source": "tushare", "rate_limit_group": "cyq", "batch_size": 200},
    },
    {
        "id": "ths_member",
        "label": "题材成分",
        "capability": "概念/行业成分",
        "dependencies": ["stock_basic"],
        "freshness_policy": "long_lived",
        "coverage_policy": {"denominator": "board", "min_rows": 1},
        "request_policy": {"source": "tushare", "rate_limit_group": "ths"},
    },
    {
        "id": "board_moneyflow",
        "label": "板块热力 / 资金",
        "capability": "板块热力",
        "dependencies": ["ths_member", "history_qfq"],
        "freshness_policy": "daily",
        "coverage_policy": {"denominator": "board", "min_rows": 1},
        "request_policy": {"source": "tushare", "rate_limit_group": "ths"},
    },
    {
        "id": "top_list",
        "label": "龙虎榜",
        "capability": "龙虎榜/游资",
        "dependencies": ["history_qfq"],
        "freshness_policy": "event",
        "coverage_policy": {"denominator": "event", "min_rows": 1},
        "request_policy": {"source": "tushare", "rate_limit_group": "top"},
    },
    {
        "id": "top_inst",
        "label": "机构席位",
        "capability": "龙虎榜/游资",
        "dependencies": ["history_qfq"],
        "freshness_policy": "event",
        "coverage_policy": {"denominator": "event", "min_rows": 1},
        "request_policy": {"source": "tushare", "rate_limit_group": "top"},
    },
    {
        "id": "hm_detail",
        "label": "游资明细",
        "capability": "龙虎榜/游资",
        "dependencies": ["history_qfq"],
        "freshness_policy": "event",
        "coverage_policy": {"denominator": "event", "min_rows": 1},
        "request_policy": {"source": "tushare", "rate_limit_group": "top"},
    },
    {
        "id": "market_environment",
        "label": "市场环境",
        "capability": "市场环境",
        "dependencies": ["daily_basic", "moneyflow", "limit_list_d", "board_moneyflow"],
        "freshness_policy": "daily",
        "coverage_policy": {"denominator": "dataset", "min_rows": 1},
        "request_policy": {"source": "local", "rate_limit_group": "local"},
    },
    {
        "id": "capability_refresh",
        "label": "能力口径刷新",
        "capability": "数据能力",
        "dependencies": ["market_environment"],
        "freshness_policy": "manual",
        "coverage_policy": {"denominator": "dataset", "min_rows": 1},
        "request_policy": {"source": "local", "rate_limit_group": "local"},
    },
]
DAG_PROGRESS_TERMINAL_STATUSES = {"completed", "skipped", "partial", "failed"}
HISTORY_BACKFILL_CAPABILITIES = {
    "历史 K 线",
    "RPS",
    "ST / 停牌状态",
    "振幅",
    "换手率",
}
DAILY_BASIC_BACKFILL_CAPABILITIES = {"每日指标", "流通市值"}
TUSHARE_TABLE_COLUMNS: Dict[str, List[str]] = {
    "tushare_daily_basic": [
        "code",
        "trade_date",
        "close",
        "turnover_rate",
        "turnover_rate_f",
        "volume_ratio",
        "pe",
        "pe_ttm",
        "pb",
        "ps",
        "ps_ttm",
        "dv_ratio",
        "dv_ttm",
        "total_share",
        "float_share",
        "free_share",
        "total_mv",
        "circ_mv",
        "source",
        "updated_at",
    ],
    "tushare_stk_factor": [
        "code",
        "trade_date",
        "macd",
        "kdj_k",
        "kdj_d",
        "kdj_j",
        "rsi_6",
        "rsi_12",
        "rsi_24",
        "boll_upper",
        "boll_mid",
        "boll_lower",
        "cci",
        "source",
        "updated_at",
    ],
    "tushare_moneyflow": [
        "code",
        "trade_date",
        "buy_sm_amount",
        "sell_sm_amount",
        "buy_md_amount",
        "sell_md_amount",
        "buy_lg_amount",
        "sell_lg_amount",
        "buy_elg_amount",
        "sell_elg_amount",
        "net_mf_amount",
        "main_net_amount",
        "source",
        "updated_at",
    ],
    "tushare_limit_list_d": [
        "code",
        "trade_date",
        "name",
        "close",
        "pct_chg",
        "limit_type",
        "up_stat",
        "fd_amount",
        "first_time",
        "last_time",
        "open_times",
        "source",
        "updated_at",
    ],
    "tushare_cyq_perf": [
        "code",
        "trade_date",
        "his_low",
        "his_high",
        "cost_5pct",
        "cost_15pct",
        "cost_50pct",
        "cost_85pct",
        "cost_95pct",
        "weight_avg",
        "winner_rate",
        "source",
        "updated_at",
    ],
    "tushare_cyq_chips": ["code", "trade_date", "price", "percent", "source", "updated_at"],
    "tushare_ths_member": [
        "code",
        "name",
        "con_code",
        "con_name",
        "weight",
        "in_date",
        "out_date",
        "is_new",
        "source",
        "updated_at",
    ],
    "tushare_top_list": [
        "code",
        "trade_date",
        "name",
        "close",
        "pct_change",
        "turnover_rate",
        "amount",
        "l_sell",
        "l_buy",
        "l_amount",
        "net_amount",
        "net_rate",
        "amount_rate",
        "float_values",
        "reason",
        "source",
        "updated_at",
    ],
    "tushare_top_inst": [
        "code",
        "trade_date",
        "exalter",
        "buy",
        "buy_rate",
        "sell",
        "sell_rate",
        "net_buy",
        "source",
        "updated_at",
    ],
    "tushare_hm_detail": [
        "code",
        "trade_date",
        "name",
        "hm_name",
        "buy_amount",
        "sell_amount",
        "net_amount",
        "source",
        "updated_at",
    ],
    "tushare_index_daily": [
        "index_code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "change",
        "pct_chg",
        "volume",
        "amount",
        "source",
        "updated_at",
    ],
}
MARKET_INDEX_CODES = ["000001.SH", "399107.SZ", "399006.SZ", "399300.SZ", "000905.SH", "000852.SH"]


def _tushare_realtime_configured() -> bool:
    return bool(settings.tushare_realtime_enabled and settings.tushare_token)


def _tushare_enrichment_configured() -> bool:
    return bool(settings.tushare_enrichment_enabled and settings.tushare_token)


def _tushare_history_configured() -> bool:
    return bool(settings.tushare_history_enabled and settings.tushare_token)


def _snapshot_date(value: Any, fallback: Optional[date] = None) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        text = str(value)[:10]
        try:
            return date.fromisoformat(text)
        except ValueError:
            pass
    return fallback or date.today()


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


class TaskBusy(RuntimeError):
    pass


class TushareRateLimiter:
    def __init__(self, limits: Optional[Dict[str, int]] = None):
        self.limits = limits or TUSHARE_RATE_LIMITS_PER_MINUTE
        self._lock = threading.Lock()
        self._next_at: Dict[str, float] = {}

    def acquire(self, group: str, cost: int = 1) -> None:
        limit = max(1, int(self.limits.get(group, 200)))
        interval = 60.0 / limit * max(1, cost)
        with self._lock:
            now = time.monotonic()
            next_at = self._next_at.get(group, now)
            wait = max(0.0, next_at - now)
            self._next_at[group] = max(now, next_at) + interval
        if wait > 0:
            threading.Event().wait(wait)


class UpdateService:
    def __init__(self, db: Database):
        self.db = db
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.data_service = DataService(db)
        self.intraday_service = IntradayRadarService(db)
        self.daily_brief_service = DailyBriefService(db)
        self.analysis_runner: Any = None
        self.backtest_runner: Any = None
        self._queue_lock = threading.Lock()
        self._queue_worker_active = False
        self.public_guard = SourceGuard(
            db,
            min_delay=settings.public_source_min_delay,
            max_delay=settings.public_source_max_delay,
        )
        self.baostock_guard = SourceGuard(
            db,
            min_delay=settings.baostock_min_delay,
            max_delay=settings.baostock_max_delay,
        )
        self.tushare_rate_limiter = TushareRateLimiter()

    def configure_runners(self, analysis_runner: Any = None, backtest_runner: Any = None) -> None:
        if analysis_runner is not None:
            self.analysis_runner = analysis_runner
        if backtest_runner is not None:
            self.backtest_runner = backtest_runner

    def recover_interrupted_tasks(self) -> None:
        now = datetime.utcnow()
        self.db.execute(
            """
            UPDATE task_runs
            SET status = 'failed',
                stage = '服务重启后中止',
                warning = '服务重启后中止',
                error_message = '服务重启后中止',
                finished_at = ?,
                updated_at = ?
            WHERE status = 'running'
            """,
            [now, now],
            write=True,
        )

    def kick_queue(self) -> None:
        self._ensure_queue_worker()

    def start_update(self, options: Optional[Dict[str, Any]] = None) -> str:
        task_id = f"update-{uuid.uuid4().hex[:12]}"
        self._enqueue_task(
            task_id,
            kind="update",
            stage="准备更新",
            source=None,
            summary={},
            payload=options or {},
        )
        return task_id

    def start_analysis(self, config: Dict[str, Any], analysis_runner: Any) -> str:
        self.analysis_runner = analysis_runner
        frozen_config = json.loads(json.dumps(config, ensure_ascii=False))
        task_id = f"analyze-{uuid.uuid4().hex[:12]}"
        self._enqueue_task(
            task_id,
            kind="analyze",
            stage="准备分析",
            source="本地仓库",
            summary={},
            payload={"config": frozen_config},
        )
        return task_id

    def start_backtest(self, payload: Dict[str, Any], backtest_runner: Any) -> tuple[str, str]:
        self.backtest_runner = backtest_runner
        task_id = f"backtest-{uuid.uuid4().hex[:12]}"
        run_id = f"backtest-{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        frozen_payload = json.loads(json.dumps(payload or {}, ensure_ascii=False))
        frozen_payload["config"] = normalize_strategy_config(frozen_payload.get("config") or {})
        frozen_payload["run_id"] = run_id
        self._enqueue_task(
            task_id,
            kind="backtest",
            stage="准备回测",
            source="本地仓库",
            summary={"backtest_run_id": run_id},
            payload=frozen_payload,
            started_at=now,
        )
        self.db.upsert(
            "backtest_runs",
            [
                {
                    "id": run_id,
                    "status": "queued",
                    "started_at": now,
                    "finished_at": None,
                    "config_json": json.dumps(frozen_payload["config"], ensure_ascii=False),
                    "summary_json": "{}",
                    "error_message": None,
                }
            ],
            ["id"],
        )
        return task_id, run_id

    def start_signal_evaluation(self, payload: Dict[str, Any], backtest_runner: Any) -> tuple[str, str]:
        return self._start_backtest_job(
            payload,
            backtest_runner,
            mode="signal_evaluation",
            task_stage="准备信号评估",
            run_prefix="signal-eval",
            run_table="backtest_runs",
        )

    def start_portfolio_backtest(self, payload: Dict[str, Any], backtest_runner: Any) -> tuple[str, str]:
        return self._start_backtest_job(
            payload,
            backtest_runner,
            mode="portfolio",
            task_stage="准备组合回测",
            run_prefix="portfolio",
            run_table="portfolio_backtest_runs",
        )

    def _start_backtest_job(
        self,
        payload: Dict[str, Any],
        backtest_runner: Any,
        mode: str,
        task_stage: str,
        run_prefix: str,
        run_table: str,
    ) -> tuple[str, str]:
        self.backtest_runner = backtest_runner
        task_id = f"backtest-{uuid.uuid4().hex[:12]}"
        run_id = f"{run_prefix}-{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        frozen_payload = json.loads(json.dumps(payload or {}, ensure_ascii=False))
        frozen_payload["config"] = normalize_strategy_config(frozen_payload.get("config") or {})
        frozen_payload["run_id"] = run_id
        frozen_payload["backtest_mode"] = mode
        self._enqueue_task(
            task_id,
            kind="backtest",
            stage=task_stage,
            source="本地仓库",
            summary={"backtest_run_id": run_id, "backtest_mode": mode},
            payload=frozen_payload,
            started_at=now,
        )
        self.db.upsert(
            run_table,
            [
                {
                    "id": run_id,
                    "status": "queued",
                    "started_at": now,
                    "finished_at": None,
                    "config_json": json.dumps(frozen_payload, ensure_ascii=False),
                    "summary_json": "{}",
                    "error_message": None,
                }
            ],
            ["id"],
        )
        return task_id, run_id

    def start_intraday_sample(self, options: Optional[Dict[str, Any]] = None) -> str:
        existing = self.db.scalar(
            """
            SELECT id
            FROM task_runs
            WHERE kind = 'intraday'
              AND status IN ('queued', 'running')
            ORDER BY started_at
            LIMIT 1
            """
        )
        if existing:
            return str(existing)
        task_id = f"intraday-{uuid.uuid4().hex[:12]}"
        self._enqueue_task(
            task_id,
            kind="intraday",
            stage="准备盘中采样",
            source="Tushare 实时日线" if _tushare_realtime_configured() else "AkShare 新浪",
            summary={},
            payload=options or {},
        )
        return task_id

    def start_scheduled_intraday_sample(self, sample_at: datetime) -> Optional[str]:
        slot = sample_at.replace(second=0, microsecond=0)
        task_id = f"intraday-auto-{slot:%Y%m%d-%H%M}"
        if self.db.scalar("SELECT id FROM task_runs WHERE id = ?", [task_id]):
            return None
        existing = self.db.scalar(
            """
            SELECT id
            FROM task_runs
            WHERE kind = 'intraday'
              AND status IN ('queued', 'running')
            ORDER BY started_at
            LIMIT 1
            """
        )
        if existing:
            return None
        schedule_key = slot.strftime("%Y-%m-%d %H:%M")
        self._enqueue_task(
            task_id,
            kind="intraday",
            stage="准备盘中采样",
            source="Tushare 实时日线" if _tushare_realtime_configured() else "AkShare 新浪",
            summary={"schedule_key": schedule_key, "scheduled": True},
            payload={
                "sample_at": slot.isoformat(timespec="seconds"),
                "schedule_key": schedule_key,
                "scheduled": True,
            },
        )
        return task_id

    def ensure_daily_brief(self) -> Optional[str]:
        existing = self.db.scalar(
            """
            SELECT id
            FROM task_runs
            WHERE kind = 'brief'
              AND status IN ('queued', 'running')
            ORDER BY started_at
            LIMIT 1
            """
        )
        if existing:
            return str(existing)
        latest = self.daily_brief_service.latest()
        if latest and not self.daily_brief_service.should_regenerate(latest):
            return None
        reason = "llm_configured_retry" if latest else "empty"
        return self.start_daily_brief({"reason": reason})

    def start_daily_brief(self, options: Optional[Dict[str, Any]] = None) -> str:
        task_id = f"brief-{uuid.uuid4().hex[:12]}"
        self._enqueue_task(
            task_id,
            kind="brief",
            stage="准备资讯简报",
            source="多源资讯",
            summary={},
            payload=options or {},
        )
        return task_id

    def start_scheduled_daily_brief(self, scheduled_at: datetime) -> Optional[str]:
        brief_date = scheduled_at.date()
        task_id = f"brief-auto-{brief_date:%Y%m%d}-{scheduled_at:%H%M}"
        if self.db.scalar("SELECT id FROM task_runs WHERE id = ?", [task_id]):
            return None
        self._enqueue_task(
            task_id,
            kind="brief",
            stage="准备资讯简报",
            source="多源资讯",
            summary={"scheduled": True, "schedule_key": scheduled_at.strftime("%Y-%m-%d %H:%M")},
            payload={
                "scheduled": True,
                "report_date": brief_date.isoformat(),
                "schedule_key": scheduled_at.strftime("%Y-%m-%d %H:%M"),
            },
        )
        return task_id

    def _enqueue_task(
        self,
        task_id: str,
        kind: str,
        stage: str,
        source: Optional[str],
        summary: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        started_at: Optional[datetime] = None,
    ) -> None:
        self._write_task(
            task_id,
            kind=kind,
            status="queued",
            stage=stage,
            source=source,
            current_stock=None,
            total=0,
            processed=0,
            success=0,
            failed=0,
            skipped=0,
            warning=None,
            summary=summary or {},
            payload=payload or {},
            error_message=None,
            started_at=started_at or datetime.utcnow(),
        )
        self._ensure_queue_worker()

    def _ensure_queue_worker(self) -> None:
        with self._queue_lock:
            if self._queue_worker_active:
                return
            self._queue_worker_active = True
        try:
            self.executor.submit(self._drain_queue)
        except Exception:
            with self._queue_lock:
                self._queue_worker_active = False
            raise

    def _drain_queue(self) -> None:
        try:
            while True:
                task = self._next_queued_task()
                if not task:
                    return
                task_id = task["id"]
                payload = json.loads(task.get("payload_json") or "{}")
                self._patch_task(task_id, status="running", warning=None, error_message=None)
                try:
                    self._dispatch_queued_task(task, payload)
                except Exception as exc:
                    self._patch_task(
                        task_id,
                        status="failed",
                        stage="任务失败",
                        failed=1,
                        warning=str(exc),
                        error_message=str(exc),
                        finished_at=datetime.utcnow(),
                    )
                self._complete_if_still_running(task_id)
        finally:
            with self._queue_lock:
                self._queue_worker_active = False
            if self.db.scalar("SELECT COUNT(*) FROM task_runs WHERE status = 'queued'"):
                self._ensure_queue_worker()

    def _next_queued_task(self) -> Optional[Dict[str, Any]]:
        rows = self.db.query(
            """
            SELECT *
            FROM task_runs
            WHERE status = 'queued'
            ORDER BY queue_order NULLS LAST, started_at, id
            LIMIT 1
            """
        )
        return rows[0] if rows else None

    def _dispatch_queued_task(self, task: Dict[str, Any], payload: Dict[str, Any]) -> None:
        kind = task.get("kind")
        task_id = task["id"]
        if kind == "update":
            self._run_update(task_id, payload)
            return
        if kind == "analyze":
            if self.analysis_runner is None:
                raise RuntimeError("分析服务尚未就绪。")
            self._run_analysis(task_id, payload.get("config") or {}, self.analysis_runner)
            return
        if kind == "intraday":
            self._run_intraday_sample(task_id, payload)
            return
        if kind == "backtest":
            if self.backtest_runner is None:
                raise RuntimeError("回测服务尚未就绪。")
            backtest_mode = payload.get("backtest_mode")
            if backtest_mode == "signal_evaluation":
                self.backtest_runner.run_signal_evaluation(payload, run_id=payload.get("run_id"), task_id=task_id)
            elif backtest_mode == "portfolio":
                self.backtest_runner.run_portfolio_backtest(payload, run_id=payload.get("run_id"), task_id=task_id)
            else:
                self.backtest_runner.run(payload, run_id=payload.get("run_id"), task_id=task_id)
            return
        if kind == "brief":
            self._run_daily_brief(task_id, payload)
            return
        raise RuntimeError(f"未知任务类型：{kind}")

    def _complete_if_still_running(self, task_id: str) -> None:
        status = self.db.scalar("SELECT status FROM task_runs WHERE id = ?", [task_id])
        if status != "running":
            return
        self._patch_task(
            task_id,
            status="completed_full",
            stage="任务完成",
            finished_at=datetime.utcnow(),
        )

    def probe_sources(self, options: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        options = options or {}
        include_bj = bool(options.get("include_bj", settings.include_bj))
        exclude_star = bool(options.get("exclude_star_board", settings.exclude_star_board))
        results = []
        probes = [
            (
                self.baostock_guard,
                "Baostock",
                "股票基础信息",
                lambda: BaostockSource().fetch_stock_basics(include_bj=include_bj, exclude_star=exclude_star),
            ),
            (
                self.public_guard,
                "AkShare 新浪",
                "当天行情快照",
                lambda: AkShareSource().fetch_sina_snapshot(include_bj=include_bj, exclude_star=exclude_star),
            ),
            (
                self.public_guard,
                "AkShare 腾讯",
                "当天行情快照",
                lambda: AkShareSource().fetch_tencent_snapshot(include_bj=include_bj, exclude_star=exclude_star),
            ),
        ]
        if _tushare_realtime_configured():
            probes.insert(
                1,
                (
                    self.public_guard,
                    "Tushare 实时日线",
                    "盘中行情快照",
                    lambda: TushareRealtimeSource().fetch_realtime_daily(
                        include_bj=include_bj,
                        exclude_star=exclude_star,
                    ),
                ),
            )
        for guard, source, capability, fetcher in probes:
            result = guard.call(
                source,
                capability,
                fetcher,
                ttl_minutes=settings.source_probe_ttl_minutes,
                max_attempts=1,
                ignore_circuit=True,
            )
            results.append(
                {
                    "source": source,
                    "capability": capability,
                    "status": result.status,
                    "rows": len(result.frame) if not result.frame.empty else 0,
                    "message": result.message,
                }
            )
        self.data_service.refresh_capabilities()
        return results

    def _run_analysis(self, task_id: str, config: Dict[str, Any], analysis_runner: Any) -> None:
        try:
            def progress(stage: str, processed: int, total: int) -> None:
                self._patch_task(
                    task_id,
                    stage=stage,
                    source="本地仓库",
                    processed=processed,
                    total=total,
                )

            run_id = analysis_runner.run(config, progress=progress)
            candidates = self.data_service.candidates(run_id, limit=1)
            self._patch_task(
                task_id,
                status="completed_full",
                stage="分析完成",
                processed=7,
                total=7,
                success=1,
                summary={
                    "analysis_run_id": run_id,
                    "candidate_count": len(candidates.get("rows", [])),
                    "zero_reason": candidates.get("zero_reason"),
                },
                finished_at=datetime.utcnow(),
            )
        except Exception as exc:
            self._patch_task(
                task_id,
                status="failed",
                stage="分析失败",
                failed=1,
                error_message=str(exc),
                warning=str(exc),
                finished_at=datetime.utcnow(),
            )

    def _run_update(self, task_id: str, options: Dict[str, Any]) -> None:
        if options.get("mode") == "capability_backfill":
            self._run_capability_backfill(task_id, options)
            return
        if options.get("mode") == "market_environment":
            self._run_market_environment_update(task_id)
            return

        force = bool(options.get("force"))
        light = options.get("mode") == "daily_light" or bool(options.get("daily_light"))
        include_bj = bool(options.get("include_bj", settings.include_bj))
        exclude_star = bool(options.get("exclude_star_board", settings.exclude_star_board))
        limit = int(options.get("limit") or settings.update_limit or 0)
        warnings: List[str] = []
        failed_sources = 0
        success_sources = 0
        target_history_date = self._target_history_date()
        start = target_history_date - timedelta(days=settings.default_history_days)
        end = target_history_date
        try:
            self._patch_task(task_id, stage="刷新股票池", source="Baostock")
            self.record_checkpoint(task_id, "stock_basic", "股票基础信息", target_history_date, "all", "running")
            try:
                stock_count = self._update_basics(force, include_bj, exclude_star, warnings)
                self.record_checkpoint(
                    task_id,
                    "stock_basic",
                    "股票基础信息",
                    target_history_date,
                    "all",
                    "completed" if stock_count else "partial",
                    rows_written=stock_count,
                )
            except Exception as exc:
                self.record_checkpoint(task_id, "stock_basic", "股票基础信息", target_history_date, "all", "failed", error_message=str(exc))
                raise
            success_sources += 1 if stock_count else 0

            self._patch_task(
                task_id,
                stage="刷新快照",
                source="Tushare 实时日线" if _tushare_realtime_configured() else "AkShare 新浪",
            )
            self.record_checkpoint(task_id, "daily_snapshot", "当天行情快照", target_history_date, "all", "running")
            try:
                snapshot_count = self._update_snapshots(force or light, include_bj, exclude_star, warnings)
                self.record_checkpoint(
                    task_id,
                    "daily_snapshot",
                    "当天行情快照",
                    target_history_date,
                    "all",
                    "completed" if snapshot_count else "partial",
                    rows_written=snapshot_count,
                    payload={
                        "source": "Tushare 实时日线" if _tushare_realtime_configured() else "AkShare 新浪",
                        "warnings": warnings[-2:],
                    },
                )
            except Exception as exc:
                self.record_checkpoint(task_id, "daily_snapshot", "当天行情快照", target_history_date, "all", "failed", error_message=str(exc))
                raise
            if snapshot_count:
                success_sources += 1
            else:
                failed_sources += 1

            incremental_history = light and not force
            stocks = self._history_stocks_for_update(
                limit=limit,
                light=incremental_history,
                target_history_date=target_history_date,
            )
            total = len(stocks)
            self._patch_task(
                task_id,
                stage="轻量补齐历史 K 线" if incremental_history else "刷新历史 K 线",
                source="Tushare daily 前复权" if _tushare_history_configured() else "Baostock",
                total=total,
            )
            self.record_checkpoint(
                task_id,
                "history_qfq",
                "历史 K 线",
                target_history_date,
                "all",
                "running",
                payload={"stock_count": total, "source": "Tushare daily 前复权" if _tushare_history_configured() else "Baostock"},
            )
            try:
                history_success, history_failed, history_skipped = self._update_history(
                    stocks,
                    start,
                    end,
                    force,
                    task_id,
                    incremental=incremental_history,
                    target_history_date=target_history_date,
                )
                self.record_checkpoint(
                    task_id,
                    "history_qfq",
                    "历史 K 线",
                    target_history_date,
                    "all",
                    "completed" if history_failed == 0 else "partial",
                    rows_written=history_success,
                    payload={"failed": history_failed, "skipped": history_skipped},
                )
            except Exception as exc:
                self.record_checkpoint(task_id, "history_qfq", "历史 K 线", target_history_date, "all", "failed", error_message=str(exc))
                raise
            if history_success:
                success_sources += 1
            if history_failed:
                failed_sources += 1

            tushare_counts: Dict[str, int] = {}
            if _tushare_enrichment_configured():
                self._patch_task(task_id, stage="刷新 Tushare 增强数据", source="Tushare Pro")
                tushare_counts = self._update_tushare_enrichment(
                    target_history_date,
                    include_bj=include_bj,
                    exclude_star=exclude_star,
                    warnings=warnings,
                    task_id=task_id,
                )
                if sum(tushare_counts.values()):
                    success_sources += 1
            else:
                self._record_tushare_enrichment_skips(task_id, target_history_date, "tushare_not_configured")

            self._patch_task(task_id, stage="刷新市场环境", source="Tushare 指数 / 本地宽度")
            self.record_checkpoint(task_id, "market_environment", "市场环境", target_history_date, "all", "running")
            try:
                market_environment_count = self._update_market_environment(target_history_date)
                self.record_checkpoint(
                    task_id,
                    "market_environment",
                    "市场环境",
                    target_history_date,
                    "all",
                    "completed" if market_environment_count else "partial",
                    rows_written=market_environment_count,
                )
            except Exception as exc:
                self.record_checkpoint(task_id, "market_environment", "市场环境", target_history_date, "all", "failed", error_message=str(exc))
                raise

            self._patch_task(task_id, stage="刷新流通市值", source="Tushare daily_basic / 本地缓存")
            float_count = self._update_float_values_from_snapshots()
            cleanup_counts = self.cleanup_intraday_history()

            self.record_checkpoint(task_id, "capability_refresh", "数据能力", target_history_date, "all", "running")
            self.data_service.refresh_capabilities()
            self.record_checkpoint(task_id, "capability_refresh", "数据能力", target_history_date, "all", "completed", rows_written=len(self.data_service.capabilities()))
            status = "completed_full" if failed_sources == 0 and not warnings else "completed_partial"
            self._patch_task(
                task_id,
                status=status,
                stage=("轻量日更完成" if light and status == "completed_full" else "更新完成")
                if status == "completed_full"
                else "部分完成",
                success=history_success,
                failed=history_failed,
                skipped=history_skipped,
                warning=warnings[-1] if warnings else None,
                summary={
                    "mode": "daily_light" if light else "full",
                    "stock_count": stock_count,
                    "snapshot_count": snapshot_count,
                    "history_success": history_success,
                    "history_failed": history_failed,
                    "history_skipped": history_skipped,
                    "target_history_date": target_history_date.isoformat(),
                    "tushare_enrichment": tushare_counts,
                    "market_environment_count": market_environment_count,
                    "float_market_value_count": float_count,
                    "intraday_cleanup": cleanup_counts,
                    "warnings": warnings,
                    "success_sources": success_sources,
                    "failed_sources": failed_sources,
                },
                finished_at=datetime.utcnow(),
            )
        except Exception as exc:
            self._patch_task(
                task_id,
                status="failed",
                stage="更新失败",
                failed=failed_sources + 1,
                error_message=str(exc),
                warning=str(exc),
                finished_at=datetime.utcnow(),
            )

    def _run_market_environment_update(self, task_id: str) -> None:
        target_history_date = self._target_history_date()
        try:
            self._patch_task(
                task_id,
                stage="重算市场环境",
                source="Tushare 指数 / 本地宽度",
                processed=0,
                total=len(DEFAULT_DATA_DAG),
            )
            self.record_checkpoint(task_id, "market_environment", "市场环境", target_history_date, "all", "running")
            market_environment_count = self._update_market_environment(target_history_date)
            self.record_checkpoint(
                task_id,
                "market_environment",
                "市场环境",
                target_history_date,
                "all",
                "completed" if market_environment_count else "partial",
                rows_written=market_environment_count,
            )

            self.record_checkpoint(task_id, "capability_refresh", "数据能力", target_history_date, "all", "running")
            self.data_service.refresh_capabilities()
            capability_count = len(self.data_service.capabilities())
            self.record_checkpoint(
                task_id,
                "capability_refresh",
                "数据能力",
                target_history_date,
                "all",
                "completed",
                rows_written=capability_count,
            )
            self._patch_task(
                task_id,
                status="completed_full" if market_environment_count else "completed_partial",
                stage="市场环境已重算",
                source="Tushare 指数 / 本地宽度",
                processed=len(DEFAULT_DATA_DAG),
                total=len(DEFAULT_DATA_DAG),
                success=1 if market_environment_count else 0,
                failed=0,
                skipped=0,
                summary={
                    "mode": "market_environment",
                    "target_history_date": target_history_date.isoformat(),
                    "market_environment_count": market_environment_count,
                    "capability_count": capability_count,
                },
                finished_at=datetime.utcnow(),
            )
        except Exception as exc:
            self.record_checkpoint(
                task_id,
                "market_environment",
                "市场环境",
                target_history_date,
                "all",
                "failed",
                error_message=str(exc),
            )
            self._patch_task(
                task_id,
                status="failed",
                stage="市场环境重算失败",
                failed=1,
                warning=str(exc),
                error_message=str(exc),
                finished_at=datetime.utcnow(),
            )

    def _run_capability_backfill(self, task_id: str, options: Dict[str, Any]) -> None:
        capability = str(options.get("capability") or "").strip()
        if not capability:
            raise RuntimeError("缺少补齐数据类。")
        target_date = _date_option(options.get("target_date")) or self._target_history_date()
        include_bj = bool(options.get("include_bj", settings.include_bj))
        exclude_star = bool(options.get("exclude_star_board", settings.exclude_star_board))
        batch_limit = _positive_int(options.get("limit"), settings.tushare_enrichment_code_limit or 200)
        warnings: List[str] = []

        try:
            self._patch_capability_backfill_progress(
                task_id,
                capability=capability,
                target_date=target_date,
                step="准备",
                processed=0,
                total=0,
                written=0,
                skipped=0,
            )
            result = self._backfill_capability(
                capability,
                target_date,
                include_bj=include_bj,
                exclude_star=exclude_star,
                batch_limit=batch_limit,
                task_id=task_id,
                warnings=warnings,
            )
            self.data_service.refresh_capabilities()
            failed = int(result.get("failed", 0))
            skipped = int(result.get("skipped", 0))
            status = "completed_full" if not warnings and failed == 0 and skipped == 0 else "completed_partial"
            self._patch_task(
                task_id,
                status=status,
                stage=f"{capability}补齐完成" if status == "completed_full" else f"{capability}补齐部分完成",
                source=str(result.get("source") or "本地仓库"),
                current_stock=None,
                total=int(result.get("total", 0)),
                processed=int(result.get("processed", result.get("total", 0))),
                success=int(result.get("success", 0)),
                failed=failed,
                skipped=skipped,
                warning=warnings[-1] if warnings else None,
                summary={
                    "mode": "capability_backfill",
                    "capability": capability,
                    "target_date": target_date.isoformat(),
                    "result": result,
                    "warnings": warnings,
                },
                finished_at=datetime.utcnow(),
            )
        except Exception as exc:
            self._patch_task(
                task_id,
                status="failed",
                stage=f"{capability}补齐失败",
                failed=1,
                error_message=str(exc),
                warning=str(exc),
                finished_at=datetime.utcnow(),
            )

    def _backfill_capability(
        self,
        capability: str,
        target_date: date,
        include_bj: bool,
        exclude_star: bool,
        batch_limit: int,
        task_id: str,
        warnings: List[str],
    ) -> Dict[str, Any]:
        if capability in HISTORY_BACKFILL_CAPABILITIES:
            return self._backfill_history_capability(
                capability,
                target_date,
                include_bj=include_bj,
                exclude_star=exclude_star,
                batch_limit=batch_limit,
                task_id=task_id,
            )
        if capability in DAILY_BASIC_BACKFILL_CAPABILITIES:
            source = TushareEnrichmentSource()
            self._patch_capability_backfill_progress(
                task_id,
                capability=capability,
                target_date=target_date,
                step="daily_basic",
                processed=0,
                total=1,
                written=0,
                skipped=0,
                source="Tushare daily_basic",
            )
            count = self._update_tushare_daily_basic(target_date, source, warnings)
            return {
                "source": "Tushare daily_basic",
                "success": count,
                "failed": 0,
                "skipped": 0,
                "total": 1,
                "processed": 1,
                "rows": count,
            }
        if capability == "技术因子":
            return self._backfill_simple_tushare_capability(
                capability,
                target_date,
                "tushare_stk_factor",
                "Tushare stk_factor",
                lambda source: source.fetch_stk_factor(target_date),
                ["code", "trade_date"],
                task_id,
                warnings,
            )
        if capability == "资金流向":
            return self._backfill_simple_tushare_capability(
                capability,
                target_date,
                "tushare_moneyflow",
                "Tushare moneyflow",
                lambda source: source.fetch_moneyflow(target_date),
                ["code", "trade_date"],
                task_id,
                warnings,
            )
        if capability == "涨跌停":
            return self._backfill_simple_tushare_capability(
                capability,
                target_date,
                "tushare_limit_list_d",
                "Tushare limit_list_d",
                lambda source: source.fetch_limit_list_d(target_date),
                ["code", "trade_date"],
                task_id,
                warnings,
            )
        if capability == "筹码分布":
            return self._backfill_cyq_capability(
                target_date,
                include_bj=include_bj,
                exclude_star=exclude_star,
                batch_limit=batch_limit,
                task_id=task_id,
                warnings=warnings,
            )
        if capability == "概念/行业成分":
            return self._backfill_ths_member_capability(
                include_bj=include_bj,
                exclude_star=exclude_star,
                batch_limit=batch_limit,
                task_id=task_id,
                warnings=warnings,
            )
        if capability == "龙虎榜/游资":
            return self._backfill_top_capability(target_date, task_id, warnings)
        if capability == "市场环境":
            count = self._update_market_environment(target_date)
            return {
                "source": "Tushare index_daily / 本地宽度",
                "success": count,
                "failed": 0,
                "skipped": 0,
                "total": 1,
                "processed": 1,
                "rows": count,
            }
        if capability == "当天行情快照":
            count = self._update_snapshots(True, include_bj, exclude_star, warnings)
            return {
                "source": "Tushare 实时日线",
                "success": count,
                "failed": 0,
                "skipped": 0,
                "total": 1,
                "processed": 1,
                "rows": count,
            }
        if capability == "股票基础信息":
            count = self._update_basics(True, include_bj, exclude_star, warnings)
            return {
                "source": "Baostock",
                "success": count,
                "failed": 0,
                "skipped": 0,
                "total": 1,
                "processed": 1,
                "rows": count,
            }
        raise RuntimeError(f"暂不支持补齐数据类：{capability}")

    def _backfill_history_capability(
        self,
        capability: str,
        target_date: date,
        include_bj: bool,
        exclude_star: bool,
        batch_limit: int,
        task_id: str,
    ) -> Dict[str, Any]:
        stocks = self._history_stocks_missing_for_target(
            target_date,
            include_bj=include_bj,
            exclude_star=exclude_star,
            limit=0,
        )
        total = len(stocks)
        self._patch_capability_backfill_progress(
            task_id,
            capability=capability,
            target_date=target_date,
            step="历史 K 线",
            processed=0,
            total=total,
            written=0,
            skipped=0,
            source="Tushare daily 前复权",
        )
        if not stocks:
            return {
                "source": "Tushare daily 前复权",
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "total": 0,
                "processed": 0,
                "rows": 0,
            }
        start = target_date - timedelta(days=settings.default_history_days)
        success, failed, skipped = self._update_history(
            stocks,
            start,
            target_date,
            False,
            task_id,
            incremental=True,
            target_history_date=target_date,
        )
        return {
            "source": "Tushare daily 前复权",
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "total": total,
            "processed": total,
            "rows": success,
        }

    def _backfill_simple_tushare_capability(
        self,
        capability: str,
        target_date: date,
        table: str,
        source_label: str,
        fetcher_factory: Any,
        key_columns: List[str],
        task_id: str,
        warnings: List[str],
    ) -> Dict[str, Any]:
        source = TushareEnrichmentSource()
        self._patch_capability_backfill_progress(
            task_id,
            capability=capability,
            target_date=target_date,
            step=source_label.replace("Tushare ", ""),
            processed=0,
            total=1,
            written=0,
            skipped=0,
            source=source_label,
        )
        frame = self._fetch_tushare_optional(
            source_label,
            capability,
            lambda: fetcher_factory(source),
            warnings,
        )
        count = self._persist_tushare_frame(table, frame, key_columns)
        self._patch_capability_backfill_progress(
            task_id,
            capability=capability,
            target_date=target_date,
            step="写入",
            processed=1,
            total=1,
            written=count,
            skipped=0,
            source=source_label,
        )
        return {
            "source": source_label,
            "success": count,
            "failed": 0,
            "skipped": 0,
            "total": 1,
            "processed": 1,
            "rows": count,
        }

    def _backfill_cyq_capability(
        self,
        target_date: date,
        include_bj: bool,
        exclude_star: bool,
        batch_limit: int,
        task_id: str,
        warnings: List[str],
    ) -> Dict[str, Any]:
        source = TushareEnrichmentSource()
        perf_skipped: set[str] = set()
        chip_skipped: set[str] = set()
        initial_missing = set(
            self._tushare_codes_missing_for_date(
                "tushare_cyq_perf",
                target_date,
                0,
                include_bj,
                exclude_star,
            )
        ) | set(
            self._tushare_codes_missing_for_date(
                "tushare_cyq_chips",
                target_date,
                0,
                include_bj,
                exclude_star,
            )
        )
        total = len(initial_missing)
        processed_codes: set[str] = set()
        written = 0
        while True:
            perf_codes = self._tushare_codes_missing_for_date(
                "tushare_cyq_perf",
                target_date,
                batch_limit,
                include_bj,
                exclude_star,
                exclude_codes=perf_skipped,
            )
            chip_codes = self._tushare_codes_missing_for_date(
                "tushare_cyq_chips",
                target_date,
                batch_limit,
                include_bj,
                exclude_star,
                exclude_codes=chip_skipped,
            )
            batch_codes = sorted(set(perf_codes) | set(chip_codes))[:batch_limit]
            if not batch_codes:
                break
            perf_batch = [code for code in batch_codes if code in set(perf_codes)]
            chip_batch = [code for code in batch_codes if code in set(chip_codes)]
            self._patch_capability_backfill_progress(
                task_id,
                capability="筹码分布",
                target_date=target_date,
                step="筹码批次",
                processed=len(processed_codes),
                total=total,
                written=written,
                skipped=len(perf_skipped | chip_skipped),
                source="Tushare cyq_perf / cyq_chips",
                current=",".join(batch_codes[:3]),
            )
            returned_perf: set[str] = set()
            if perf_batch:
                frame = self._fetch_tushare_optional(
                    "Tushare cyq_perf",
                    "筹码分布",
                    lambda: source.fetch_cyq_perf_for_codes(perf_batch, target_date, limit=len(perf_batch)),
                    warnings,
                )
                returned_perf = {str(row.get("code")) for row in frame.to_dict("records") if row.get("code")}
                written += self._persist_tushare_frame("tushare_cyq_perf", frame, ["code", "trade_date"])
                perf_skipped.update(set(perf_batch) - returned_perf)
            returned_chips: set[str] = set()
            if chip_batch:
                frame = self._fetch_tushare_optional(
                    "Tushare cyq_chips",
                    "筹码分布",
                    lambda: source.fetch_cyq_chips_for_codes(chip_batch, target_date, limit=len(chip_batch)),
                    warnings,
                )
                returned_chips = {str(row.get("code")) for row in frame.to_dict("records") if row.get("code")}
                written += self._persist_tushare_frame(
                    "tushare_cyq_chips",
                    frame,
                    ["code", "trade_date", "price"],
                )
                chip_skipped.update(set(chip_batch) - returned_chips)
            processed_codes.update(batch_codes)
        remaining = set(
            self._tushare_codes_missing_for_date(
                "tushare_cyq_perf",
                target_date,
                0,
                include_bj,
                exclude_star,
            )
        ) | set(
            self._tushare_codes_missing_for_date(
                "tushare_cyq_chips",
                target_date,
                0,
                include_bj,
                exclude_star,
            )
        )
        skipped = len(remaining)
        return {
            "source": "Tushare cyq_perf / cyq_chips",
            "success": written,
            "failed": 0,
            "skipped": skipped,
            "total": total,
            "processed": len(processed_codes),
            "rows": written,
        }

    def _backfill_ths_member_capability(
        self,
        include_bj: bool,
        exclude_star: bool,
        batch_limit: int,
        task_id: str,
        warnings: List[str],
    ) -> Dict[str, Any]:
        source = TushareEnrichmentSource()
        return self._update_ths_members_from_boards(
            source,
            warnings,
            task_id=task_id,
            limit=0,
            target_date=None,
            include_bj=include_bj,
            exclude_star=exclude_star,
        )

    def _update_ths_members_from_boards(
        self,
        source: TushareEnrichmentSource,
        warnings: List[str],
        task_id: Optional[str] = None,
        limit: int = 0,
        target_date: Optional[date] = None,
        missing_only: bool = False,
        include_bj: bool = False,
        exclude_star: bool = False,
    ) -> Dict[str, Any]:
        board_frame = self._fetch_tushare_optional(
            "Tushare ths_index",
            "概念/行业成分",
            lambda: source.fetch_ths_index(limit=0),
            warnings,
        )
        board_records = board_frame.to_dict("records") if board_frame is not None and not board_frame.empty else []
        if missing_only:
            existing_boards = {
                str(row["con_code"])
                for row in self.db.query("SELECT DISTINCT con_code FROM tushare_ths_member WHERE con_code IS NOT NULL")
                if row.get("con_code")
            }
            board_records = [
                board
                for board in board_records
                if str(board.get("ts_code") or board.get("code") or "").strip() not in existing_boards
            ]
        if limit > 0:
            board_records = board_records[:limit]
        total = len(board_records)
        written = 0
        skipped = 0
        for index, board in enumerate(board_records, start=1):
            board_code = str(board.get("ts_code") or board.get("code") or "").strip()
            if not board_code:
                skipped += 1
                continue
            board_name = str(board.get("name") or board_code)
            if task_id:
                self._patch_capability_backfill_progress(
                    task_id,
                    capability="概念/行业成分",
                    target_date=target_date,
                    step="ths_member",
                    processed=index - 1,
                    total=total,
                    written=written,
                    skipped=skipped,
                    source="Tushare ths_member",
                    current=f"{board_code} {board_name}",
                )
            frame = self._fetch_tushare_optional(
                "Tushare ths_member",
                "概念/行业成分",
                lambda board_code=board_code, board_name=board_name: source.fetch_ths_member_for_board(
                    board_code,
                    board_name,
                    include_bj=include_bj,
                    exclude_star=exclude_star,
                ),
                warnings,
            )
            if frame is None or frame.empty:
                skipped += 1
                continue
            written += self._persist_tushare_frame("tushare_ths_member", frame, ["code", "con_code"])
        return {
            "source": "Tushare ths_member",
            "success": written,
            "failed": 0,
            "skipped": skipped,
            "total": total,
            "processed": total,
            "rows": written,
        }

    def _backfill_top_capability(
        self,
        target_date: date,
        task_id: str,
        warnings: List[str],
    ) -> Dict[str, Any]:
        source = TushareEnrichmentSource()
        specs = [
            ("tushare_top_list", "Tushare top_list", lambda: source.fetch_top_list(target_date), ["code", "trade_date", "reason"]),
            ("tushare_top_inst", "Tushare top_inst", lambda: source.fetch_top_inst(target_date), ["code", "trade_date", "exalter"]),
            ("tushare_hm_detail", "Tushare hm_detail", lambda: source.fetch_hm_detail(target_date), ["code", "trade_date", "hm_name"]),
        ]
        written = 0
        for index, (table, source_label, fetcher, keys) in enumerate(specs, start=1):
            self._patch_capability_backfill_progress(
                task_id,
                capability="龙虎榜/游资",
                target_date=target_date,
                step=source_label.replace("Tushare ", ""),
                processed=index - 1,
                total=len(specs),
                written=written,
                skipped=0,
                source=source_label,
            )
            frame = self._fetch_tushare_optional(source_label, "龙虎榜/游资", fetcher, warnings)
            written += self._persist_tushare_frame(table, frame, keys)
        return {
            "source": "Tushare 龙虎榜/游资",
            "success": written,
            "failed": 0,
            "skipped": 0,
            "total": len(specs),
            "processed": len(specs),
            "rows": written,
        }

    def _patch_capability_backfill_progress(
        self,
        task_id: str,
        capability: str,
        target_date: Optional[date],
        step: str,
        processed: int,
        total: int,
        written: int,
        skipped: int,
        source: str = "本地仓库",
        current: Optional[str] = None,
    ) -> None:
        summary = {
            "backfill_progress": {
                "mode": "capability_backfill",
                "capability": capability,
                "target_date": target_date.isoformat() if target_date else None,
                "step": step,
                "written_rows": written,
                "skipped": skipped,
                "last_heartbeat_at": datetime.utcnow().isoformat(timespec="seconds"),
            }
        }
        self._patch_task(
            task_id,
            stage=f"补齐{capability}",
            source=source,
            current_stock=current or step,
            total=total,
            processed=processed,
            success=written,
            skipped=skipped,
            summary=summary,
        )

    def _update_tushare_enrichment(
        self,
        trade_date: date,
        include_bj: bool,
        exclude_star: bool,
        warnings: List[str],
        task_id: Optional[str] = None,
    ) -> Dict[str, int]:
        source = TushareEnrichmentSource()
        limit = max(0, int(settings.tushare_enrichment_code_limit or 0))
        counts: Dict[str, int] = {}

        counts["daily_basic"] = self._maybe_update_stock_capability(
            task_id,
            "daily_basic",
            "每日指标",
            "tushare_daily_basic",
            trade_date,
            0.95,
            lambda: self._update_tushare_daily_basic(trade_date, source, warnings),
        )
        counts["stk_factor"] = self._maybe_update_stock_capability(
            task_id,
            "stk_factor",
            "技术因子",
            "tushare_stk_factor",
            trade_date,
            0.95,
            lambda: self._persist_tushare_frame(
                "tushare_stk_factor",
                self._fetch_tushare_optional(
                    "Tushare stk_factor",
                    "技术因子",
                    lambda: source.fetch_stk_factor(trade_date),
                    warnings,
                ),
                ["code", "trade_date"],
            ),
        )
        counts["moneyflow"] = self._maybe_update_stock_capability(
            task_id,
            "moneyflow",
            "资金流向",
            "tushare_moneyflow",
            trade_date,
            0.90,
            lambda: self._persist_tushare_frame(
                "tushare_moneyflow",
                self._fetch_tushare_optional(
                    "Tushare moneyflow",
                    "资金流向",
                    lambda: source.fetch_moneyflow(trade_date),
                    warnings,
                ),
                ["code", "trade_date"],
            ),
        )
        counts["limit_list_d"] = self._maybe_update_event_capability(
            task_id,
            "limit_list_d",
            "涨跌停",
            "tushare_limit_list_d",
            trade_date,
            lambda: self._persist_tushare_frame(
                "tushare_limit_list_d",
                self._fetch_tushare_optional(
                    "Tushare limit_list_d",
                    "涨跌停",
                    lambda: source.fetch_limit_list_d(trade_date),
                    warnings,
                ),
                ["code", "trade_date"],
            ),
        )
        cyq_perf_codes = self._tushare_codes_missing_for_date(
            "tushare_cyq_perf",
            trade_date,
            limit,
            include_bj=include_bj,
            exclude_star=exclude_star,
        )
        if cyq_perf_codes:
            if task_id:
                self.record_checkpoint(task_id, "cyq_perf", "筹码分布", trade_date, "all", "running", payload={"codes": len(cyq_perf_codes)})
            try:
                counts["cyq_perf"] = self._persist_tushare_frame(
                    "tushare_cyq_perf",
                    self._fetch_tushare_optional(
                        "Tushare cyq_perf",
                        "筹码分布",
                        lambda: source.fetch_cyq_perf_for_codes(cyq_perf_codes, trade_date, limit=limit),
                        warnings,
                    ),
                    ["code", "trade_date"],
                )
                if task_id:
                    self.record_checkpoint(task_id, "cyq_perf", "筹码分布", trade_date, "all", "completed", rows_written=counts["cyq_perf"])
            except Exception as exc:
                if task_id:
                    self.record_checkpoint(task_id, "cyq_perf", "筹码分布", trade_date, "all", "failed", error_message=str(exc))
                raise
        else:
            counts["cyq_perf"] = 0
            if task_id:
                self.record_checkpoint(task_id, "cyq_perf", "筹码分布", trade_date, "all", "skipped", payload={"reason": "coverage_complete"})
        cyq_chip_codes = self._tushare_codes_missing_for_date(
            "tushare_cyq_chips",
            trade_date,
            limit,
            include_bj=include_bj,
            exclude_star=exclude_star,
        )
        if cyq_chip_codes:
            if task_id:
                self.record_checkpoint(task_id, "cyq_chips", "筹码分布", trade_date, "all", "running", payload={"codes": len(cyq_chip_codes)})
            try:
                counts["cyq_chips"] = self._persist_tushare_frame(
                    "tushare_cyq_chips",
                    self._fetch_tushare_optional(
                        "Tushare cyq_chips",
                        "筹码分布",
                        lambda: source.fetch_cyq_chips_for_codes(cyq_chip_codes, trade_date, limit=limit),
                        warnings,
                    ),
                    ["code", "trade_date", "price"],
                )
                if task_id:
                    self.record_checkpoint(task_id, "cyq_chips", "筹码分布", trade_date, "all", "completed", rows_written=counts["cyq_chips"])
            except Exception as exc:
                if task_id:
                    self.record_checkpoint(task_id, "cyq_chips", "筹码分布", trade_date, "all", "failed", error_message=str(exc))
                raise
        else:
            counts["cyq_chips"] = 0
            if task_id:
                self.record_checkpoint(task_id, "cyq_chips", "筹码分布", trade_date, "all", "skipped", payload={"reason": "coverage_complete"})
        if task_id:
            self.record_checkpoint(task_id, "ths_member", "概念/行业成分", trade_date, "all", "running")
        try:
            ths_result = self._update_ths_members_from_boards(
                source,
                warnings,
                limit=limit,
                target_date=None,
                missing_only=True,
                include_bj=include_bj,
                exclude_star=exclude_star,
            )
            if task_id:
                self.record_checkpoint(
                    task_id,
                    "ths_member",
                    "概念/行业成分",
                    trade_date,
                    "all",
                    "completed" if int(ths_result.get("success", 0)) else "skipped",
                    rows_written=int(ths_result.get("success", 0)),
                    payload={"skipped": ths_result.get("skipped", 0), "reason": "coverage_complete" if not int(ths_result.get("success", 0)) else None},
                )
        except Exception as exc:
            if task_id:
                self.record_checkpoint(task_id, "ths_member", "概念/行业成分", trade_date, "all", "failed", error_message=str(exc))
            raise
        counts["ths_member"] = int(ths_result.get("success", 0))
        counts["board_moneyflow"] = self._update_market_sector_daily(trade_date, source, warnings, task_id=task_id)
        counts["top_list"] = self._maybe_update_event_capability(
            task_id,
            "top_list",
            "龙虎榜/游资",
            "tushare_top_list",
            trade_date,
            lambda: self._persist_tushare_frame(
                "tushare_top_list",
                self._fetch_tushare_optional(
                    "Tushare top_list",
                    "龙虎榜/游资",
                    lambda: source.fetch_top_list(trade_date),
                    warnings,
                ),
                ["code", "trade_date", "reason"],
            ),
        )
        counts["top_inst"] = self._maybe_update_event_capability(
            task_id,
            "top_inst",
            "龙虎榜/游资",
            "tushare_top_inst",
            trade_date,
            lambda: self._persist_tushare_frame(
                "tushare_top_inst",
                self._fetch_tushare_optional(
                    "Tushare top_inst",
                    "龙虎榜/游资",
                    lambda: source.fetch_top_inst(trade_date),
                    warnings,
                ),
                ["code", "trade_date", "exalter"],
            ),
        )
        counts["hm_detail"] = self._maybe_update_event_capability(
            task_id,
            "hm_detail",
            "龙虎榜/游资",
            "tushare_hm_detail",
            trade_date,
            lambda: self._persist_tushare_frame(
                "tushare_hm_detail",
                self._fetch_tushare_optional(
                    "Tushare hm_detail",
                    "龙虎榜/游资",
                    lambda: source.fetch_hm_detail(trade_date),
                    warnings,
                ),
                ["code", "trade_date", "hm_name"],
            ),
        )
        return counts

    def record_checkpoint(
        self,
        task_id: str,
        job_id: str,
        capability: str,
        target_date: Optional[date],
        batch_key: str,
        status: str,
        rows_written: int = 0,
        error_message: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
    ) -> None:
        now = datetime.utcnow()
        existing = self.db.query("SELECT started_at FROM update_checkpoints WHERE id = ?", [f"{task_id}:{job_id}:{batch_key}"])
        existing_started_at = existing[0].get("started_at") if existing else None
        self.db.upsert(
            "update_checkpoints",
            [
                {
                    "id": f"{task_id}:{job_id}:{batch_key}",
                    "task_id": task_id,
                    "job_id": job_id,
                    "capability": capability,
                    "target_date": target_date,
                    "batch_key": batch_key,
                    "status": status,
                    "rows_written": rows_written,
                    "started_at": started_at or existing_started_at or now,
                    "finished_at": finished_at if finished_at is not None else (now if status in {"completed", "skipped", "partial", "failed"} else None),
                    "error_message": error_message,
                    "payload_json": payload or {},
                }
            ],
            ["id"],
        )
        self._sync_task_progress_from_checkpoints(task_id)

    def _sync_task_progress_from_checkpoints(self, task_id: str) -> None:
        task_rows = self.db.query("SELECT kind, payload_json FROM task_runs WHERE id = ?", [task_id])
        if not task_rows or task_rows[0].get("kind") != "update":
            return
        try:
            payload = json.loads(task_rows[0].get("payload_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            payload = {}
        if payload.get("mode") == "capability_backfill":
            return

        dag_ids = [node["id"] for node in DEFAULT_DATA_DAG]
        checkpoints = self.db.query(
            """
            SELECT job_id, status
            FROM update_checkpoints
            WHERE task_id = ?
            """,
            [task_id],
        )
        status_by_job = {row["job_id"]: str(row.get("status") or "") for row in checkpoints if row.get("job_id") in dag_ids}
        processed = sum(1 for job_id in dag_ids if status_by_job.get(job_id) in DAG_PROGRESS_TERMINAL_STATUSES)
        self._patch_task(task_id, processed=processed, total=len(dag_ids))

    def _record_tushare_enrichment_skips(self, task_id: str, target_date: date, reason: str) -> None:
        for job_id, capability in [
            ("daily_basic", "每日指标"),
            ("stk_factor", "技术因子"),
            ("moneyflow", "资金流向"),
            ("limit_list_d", "涨跌停"),
            ("cyq_perf", "筹码分布"),
            ("cyq_chips", "筹码分布"),
            ("ths_member", "概念/行业成分"),
            ("board_moneyflow", "板块热力"),
            ("top_list", "龙虎榜/游资"),
            ("top_inst", "龙虎榜/游资"),
            ("hm_detail", "龙虎榜/游资"),
        ]:
            self.record_checkpoint(
                task_id,
                job_id,
                capability,
                target_date,
                "all",
                "skipped",
                rows_written=0,
                payload={"reason": reason},
            )

    def _maybe_update_stock_capability(
        self,
        task_id: Optional[str],
        job_id: str,
        capability: str,
        table: str,
        trade_date: date,
        min_ratio: float,
        updater: Any,
    ) -> int:
        active_count = max(1, self.data_service.active_stock_count())
        existing = int(
            self.db.scalar(
                f"""
                SELECT COUNT(DISTINCT t.code)
                FROM {table} t
                JOIN stock_basic b ON b.code = t.code
                WHERE t.trade_date = ?
                  AND b.suspended IS DISTINCT FROM TRUE
                """,
                [trade_date],
            )
            or 0
        )
        if existing / active_count >= min_ratio:
            if task_id:
                self.record_checkpoint(
                    task_id,
                    job_id,
                    capability,
                    trade_date,
                    "all",
                    "skipped",
                    rows_written=0,
                    payload={"reason": "coverage_complete", "coverage_count": existing, "denominator": active_count},
                )
            return existing
        if task_id:
            self.record_checkpoint(task_id, job_id, capability, trade_date, "all", "running", rows_written=0)
        try:
            written = int(updater() or 0)
            if task_id:
                self.record_checkpoint(task_id, job_id, capability, trade_date, "all", "completed", rows_written=written)
            return written
        except Exception as exc:
            if task_id:
                self.record_checkpoint(task_id, job_id, capability, trade_date, "all", "failed", error_message=str(exc))
            raise

    def _maybe_update_event_capability(
        self,
        task_id: Optional[str],
        job_id: str,
        capability: str,
        table: str,
        trade_date: date,
        updater: Any,
    ) -> int:
        existing = int(self.db.scalar(f"SELECT COUNT(*) FROM {table} WHERE trade_date = ?", [trade_date]) or 0)
        if existing:
            if task_id:
                self.record_checkpoint(
                    task_id,
                    job_id,
                    capability,
                    trade_date,
                    "all",
                    "skipped",
                    payload={"reason": "event_date_already_loaded", "rows": existing},
                )
            return existing
        if task_id:
            self.record_checkpoint(task_id, job_id, capability, trade_date, "all", "running")
        try:
            written = int(updater() or 0)
            if task_id:
                self.record_checkpoint(task_id, job_id, capability, trade_date, "all", "completed", rows_written=written)
            return written
        except Exception as exc:
            if task_id:
                self.record_checkpoint(task_id, job_id, capability, trade_date, "all", "failed", error_message=str(exc))
            raise

    def _update_market_sector_daily(
        self,
        trade_date: date,
        source: TushareEnrichmentSource,
        warnings: List[str],
        task_id: Optional[str] = None,
    ) -> int:
        if self.db.scalar("SELECT COUNT(*) FROM market_sector_daily WHERE trade_date = ?", [trade_date]):
            rows = self.db.query("SELECT * FROM market_sector_daily WHERE trade_date = ?", [trade_date])
            self._attach_sector_breadth_counts(rows)
            existing = self.db.upsert("market_sector_daily", rows, ["sector_code", "sector_type", "trade_date"])
            if task_id:
                self.record_checkpoint(
                    task_id,
                    "board_moneyflow",
                    "板块热力",
                    trade_date,
                    "all",
                    "skipped",
                    payload={"reason": "sector_date_already_loaded", "rows": existing},
                )
            return existing
        if task_id:
            self.record_checkpoint(task_id, "board_moneyflow", "板块热力", trade_date, "all", "running")
        if not hasattr(source, "fetch_concept_moneyflow") or not hasattr(source, "fetch_industry_moneyflow"):
            if task_id:
                self.record_checkpoint(
                    task_id,
                    "board_moneyflow",
                    "板块热力",
                    trade_date,
                    "all",
                    "skipped",
                    payload={"reason": "sector_moneyflow_source_unavailable"},
                )
            return 0
        concept = self._fetch_tushare_optional(
            "Tushare moneyflow_cnt_ths",
            "板块热力",
            lambda: source.fetch_concept_moneyflow(trade_date),
            warnings,
        )
        industry = self._fetch_tushare_optional(
            "Tushare moneyflow_ind_ths",
            "板块热力",
            lambda: source.fetch_industry_moneyflow(trade_date),
            warnings,
        )
        count = self._persist_sector_frames([concept, industry])
        if task_id:
            self.record_checkpoint(task_id, "board_moneyflow", "板块热力", trade_date, "all", "completed", rows_written=count)
        return count

    def _persist_sector_frames(self, frames: List[pd.DataFrame]) -> int:
        rows: List[Dict[str, Any]] = []
        for frame in frames:
            if frame is None or frame.empty:
                continue
            rows.extend(frame.to_dict("records"))
        if not rows:
            return 0
        self._attach_sector_breadth_counts(rows)
        return self.db.upsert("market_sector_daily", rows, ["sector_code", "sector_type", "trade_date"])

    def _attach_sector_breadth_counts(self, rows: List[Dict[str, Any]]) -> None:
        by_date: Dict[date, List[Dict[str, Any]]] = {}
        for row in rows:
            trade_date = _date_option(row.get("trade_date"))
            if trade_date:
                by_date.setdefault(trade_date, []).append(row)
        for trade_date, dated_rows in by_date.items():
            sector_codes = sorted({str(row.get("sector_code")) for row in dated_rows if row.get("sector_code")})
            if not sector_codes:
                continue
            placeholders = ",".join(["?"] * len(sector_codes))
            limit_date = _date_option(
                self.db.scalar("SELECT MAX(trade_date) FROM tushare_limit_list_d WHERE trade_date <= ?", [trade_date])
            )
            snapshot_date = _date_option(
                self.db.scalar("SELECT MAX(date) FROM daily_snapshots WHERE date <= ?", [trade_date])
            )
            history_date = _date_option(
                self.db.scalar("SELECT MAX(date) FROM historical_bars WHERE date <= ?", [trade_date])
            )
            limit_join_date = limit_date or trade_date
            snapshot_join_date = snapshot_date or trade_date
            history_join_date = history_date or trade_date
            quote_available = bool(snapshot_date or history_date)
            quote_data_date = snapshot_date or history_date
            params: List[Any] = [limit_join_date, snapshot_join_date, history_join_date, *sector_codes]
            count_rows = self.db.query(
                f"""
                SELECT m.con_code AS sector_code,
                       COUNT(DISTINCT m.code) AS member_count,
                       COUNT(DISTINCT CASE WHEN UPPER(COALESCE(l.limit_type, '')) LIKE 'U%' THEN m.code END) AS limit_up_count,
                       COUNT(DISTINCT CASE WHEN COALESCE(s.pct_chg, h.pct_chg) >= 5 THEN m.code END) AS strong_count
                FROM tushare_ths_member m
                LEFT JOIN tushare_limit_list_d l
                  ON l.code = m.code AND l.trade_date = ?
                LEFT JOIN daily_snapshots s
                  ON s.code = m.code AND s.date = ?
                LEFT JOIN historical_bars h
                  ON h.code = m.code AND h.date = ?
                WHERE m.con_code IN ({placeholders})
                GROUP BY m.con_code
                """,
                params,
            )
            counts = {str(row["sector_code"]): row for row in count_rows}
            leader_rows = self.db.query(
                f"""
                SELECT m.con_code AS sector_code,
                       m.code,
                       COALESCE(s.name, b.name, m.name) AS name,
                       COALESCE(s.pct_chg, h.pct_chg) AS pct_chg
                FROM tushare_ths_member m
                LEFT JOIN daily_snapshots s
                  ON s.code = m.code AND s.date = ?
                LEFT JOIN historical_bars h
                  ON h.code = m.code AND h.date = ?
                LEFT JOIN stock_basic b
                  ON b.code = m.code
                WHERE m.con_code IN ({placeholders})
                  AND COALESCE(s.pct_chg, h.pct_chg) IS NOT NULL
                ORDER BY m.con_code, COALESCE(s.pct_chg, h.pct_chg) DESC
                """,
                [snapshot_join_date, history_join_date, *sector_codes],
            )
            leaders: Dict[str, Dict[str, Any]] = {}
            for leader in leader_rows:
                leaders.setdefault(str(leader["sector_code"]), leader)
            for row in dated_rows:
                code = str(row.get("sector_code") or "")
                count = counts.get(code, {})
                leader = leaders.get(code, {})
                member_count = int(count.get("member_count") or 0)
                if not member_count:
                    limit_status = "missing_members"
                    strong_status = "missing_members"
                else:
                    limit_status = "computed" if limit_date else "missing_limit_data"
                    strong_status = "computed" if quote_available else "missing_quote"
                row["member_count"] = member_count
                row["limit_up_count_status"] = limit_status
                row["strong_count_status"] = strong_status
                row["limit_up_count"] = int(count.get("limit_up_count") or 0) if limit_status == "computed" else None
                row["strong_count"] = int(count.get("strong_count") or 0) if strong_status == "computed" else None
                row["limit_data_date"] = limit_date if limit_status == "computed" else None
                row["quote_data_date"] = quote_data_date if strong_status == "computed" else None
                row["leader_code"] = row.get("leader_code") or leader.get("code")
                row["leader_name"] = row.get("leader_name") or leader.get("name")
                row["leader_pct_chg"] = leader.get("pct_chg")

    def _update_tushare_daily_basic(
        self,
        trade_date: date,
        source: Optional[TushareEnrichmentSource] = None,
        warnings: Optional[List[str]] = None,
    ) -> int:
        resolved_source = source or TushareEnrichmentSource()
        frame = self._fetch_tushare_optional(
            "Tushare daily_basic",
            "每日指标",
            lambda: resolved_source.fetch_daily_basic(trade_date),
            warnings,
        )
        count = self._persist_tushare_frame("tushare_daily_basic", frame, ["code", "trade_date"])
        float_count = self._upsert_float_market_values_from_daily_basic(frame)
        if float_count:
            self.public_guard.record(
                "Tushare daily_basic",
                "流通市值",
                "available",
                payload={"rows": float_count, "method": "daily_basic_circ_mv"},
            )
        return count

    def _update_market_environment(
        self,
        trade_date: date,
        source: Optional[TushareEnrichmentSource] = None,
    ) -> int:
        resolved_source = source or TushareEnrichmentSource()
        index_frame = self._fetch_tushare_optional(
            "Tushare index_daily",
            "市场环境",
            lambda: resolved_source.fetch_index_daily(MARKET_INDEX_CODES, trade_date),
            warnings=None,
        )
        index_count = self._persist_tushare_frame("tushare_index_daily", index_frame, ["index_code", "trade_date"])
        if index_frame is None or index_frame.empty:
            index_frame = pd.DataFrame(
                self.db.query(
                    "SELECT * FROM tushare_index_daily WHERE trade_date = ?",
                    [trade_date],
                )
            )
        environment = self._build_market_environment_row(trade_date, index_frame, index_count)
        if not environment:
            return 0
        count = self.db.upsert("market_environment", [environment], ["date"])
        self.public_guard.record(
            environment["source"],
            "市场环境",
            "available",
            payload={"rows": count, "index_rows": index_count},
        )
        return count

    def _update_realtime_market_environment(self, trade_date: date) -> int:
        bars = self.db.query(
            """
            SELECT s.pct_chg, s.amount
            FROM daily_snapshots s
            JOIN stock_basic b ON b.code = s.code
            WHERE s.date = ?
              AND b.suspended IS DISTINCT FROM TRUE
            """,
            [trade_date],
        )
        if not bars:
            return 0
        pct_values = [safe_float(row.get("pct_chg")) for row in bars]
        pct_values = [value for value in pct_values if value is not None]
        if not pct_values:
            return 0
        up_count = sum(1 for value in pct_values if value > 0)
        down_count = sum(1 for value in pct_values if value < 0)
        flat_count = max(0, len(pct_values) - up_count - down_count)
        strong_count = sum(1 for value in pct_values if value >= 5)
        weak_count = sum(1 for value in pct_values if value <= -5)
        total_amount = sum(safe_float(row.get("amount")) or 0 for row in bars)
        official_limits = self.db.query("SELECT limit_type FROM tushare_limit_list_d WHERE trade_date = ?", [trade_date])
        if official_limits:
            limit_up_count = sum(1 for row in official_limits if str(row.get("limit_type") or "").upper().startswith("U"))
            limit_down_count = sum(1 for row in official_limits if str(row.get("limit_type") or "").upper().startswith("D"))
            limit_source = "official_daily"
        else:
            limit_up_count = sum(1 for value in pct_values if value >= 9.8)
            limit_down_count = sum(1 for value in pct_values if value <= -9.8)
            limit_source = "intraday_estimate"
        index_score = 50
        breadth_score = _clamp(up_count / len(pct_values) * 100, 0, 100)
        turnover_score, turnover_ratio = self._market_turnover_score(trade_date, total_amount)
        limit_score = _clamp(50 + (limit_up_count - limit_down_count) / max(len(pct_values), 1) * 100, 0, 100)
        trend_score = round(index_score * 0.25 + breadth_score * 0.45 + turnover_score * 0.15 + limit_score * 0.15, 2)
        risk_level = "risk_on" if trend_score >= 65 else "neutral" if trend_score >= 45 else "risk_off"
        return self.db.upsert(
            "market_environment",
            [
                {
                    "date": trade_date,
                    "trend_score": trend_score,
                    "risk_level": risk_level,
                    "index_score": round(index_score, 2),
                    "breadth_score": round(breadth_score, 2),
                    "turnover_score": round(turnover_score, 2),
                    "limit_score": round(limit_score, 2),
                    "up_count": up_count,
                    "down_count": down_count,
                    "flat_count": flat_count,
                    "limit_up_count": limit_up_count,
                    "limit_down_count": limit_down_count,
                    "strong_count": strong_count,
                    "weak_count": weak_count,
                    "total_amount": total_amount,
                    "source": f"实时快照宽度 + {limit_source}",
                    "summary_json": {
                        "turnover_ratio": turnover_ratio,
                        "limit_source": limit_source,
                        "realtime": True,
                    },
                    "updated_at": datetime.utcnow(),
                }
            ],
            ["date"],
        )

    def _update_realtime_concept_heat(self, trade_date: date) -> int:
        rows = self.db.query(
            """
            WITH joined AS (
              SELECT m.con_code,
                     m.con_name,
                     s.code,
                     s.name,
                     s.pct_chg,
                     s.amount,
                     l.limit_type,
                     ROW_NUMBER() OVER (
                       PARTITION BY m.con_code
                       ORDER BY s.pct_chg DESC NULLS LAST, s.amount DESC NULLS LAST
                     ) AS rn
              FROM tushare_ths_member m
              JOIN daily_snapshots s ON s.code = m.code AND s.date = ?
              LEFT JOIN tushare_limit_list_d l ON l.code = s.code AND l.trade_date = ?
            )
            SELECT con_code AS sector_code,
                   con_name AS sector_name,
                   COUNT(*) AS company_count,
                   COUNT(*) AS member_count,
                   AVG(pct_chg) AS pct_chg,
                   SUM(amount) AS amount,
                   SUM(CASE WHEN pct_chg >= 5 THEN 1 ELSE 0 END) AS strong_count,
                   SUM(CASE WHEN UPPER(COALESCE(limit_type, '')) LIKE 'U%' THEN 1 ELSE 0 END) AS limit_up_count,
                   SUM(CASE WHEN limit_type IS NOT NULL THEN 1 ELSE 0 END) AS limit_rows,
                   MAX(CASE WHEN rn = 1 THEN code END) AS leader_code,
                   MAX(CASE WHEN rn = 1 THEN name END) AS leader_name,
                   MAX(CASE WHEN rn = 1 THEN pct_chg END) AS leader_pct_chg
            FROM joined
            GROUP BY con_code, con_name
            HAVING COUNT(*) > 0
            """,
            [trade_date, trade_date],
        )
        output = []
        for row in rows:
            pct_chg = safe_float(row.get("pct_chg")) or 0
            strong_count = int(row.get("strong_count") or 0)
            limit_rows = int(row.get("limit_rows") or 0)
            output.append(
                {
                    "sector_code": row.get("sector_code"),
                    "sector_name": row.get("sector_name"),
                    "sector_type": "concept",
                    "trade_date": trade_date,
                    "pct_chg": pct_chg,
                    "amount": row.get("amount"),
                    "net_amount": None,
                    "company_count": row.get("company_count"),
                    "member_count": row.get("member_count"),
                    "limit_up_count": int(row.get("limit_up_count") or 0) if limit_rows else None,
                    "limit_up_count_status": "computed" if limit_rows else "daily_only",
                    "strong_count": strong_count,
                    "strong_count_status": "computed",
                    "limit_data_date": trade_date if limit_rows else None,
                    "quote_data_date": trade_date,
                    "leader_code": row.get("leader_code"),
                    "leader_name": row.get("leader_name"),
                    "leader_pct_chg": row.get("leader_pct_chg"),
                    "heat_score": round(_clamp(50 + pct_chg * 4 + strong_count * 1.5, 0, 100), 2),
                    "source": "实时快照概念热度",
                    "updated_at": datetime.utcnow(),
                }
            )
        return self.db.upsert("market_sector_daily", output, ["sector_code", "sector_type", "trade_date"])

    def _build_market_environment_row(
        self,
        trade_date: date,
        index_frame: pd.DataFrame,
        index_count: int,
    ) -> Optional[Dict[str, Any]]:
        bars = self.db.query(
            """
            SELECT h.pct_chg, h.amount
            FROM historical_bars h
            JOIN stock_basic b ON b.code = h.code
            WHERE h.date = ?
              AND b.suspended IS DISTINCT FROM TRUE
            """,
            [trade_date],
        )
        limit_rows = self.db.query(
            "SELECT limit_type FROM tushare_limit_list_d WHERE trade_date = ?",
            [trade_date],
        )
        index_rows = [] if index_frame is None or index_frame.empty else index_frame.to_dict("records")
        if not bars and not index_rows:
            return None

        pct_values = [safe_float(row.get("pct_chg")) for row in bars]
        pct_values = [value for value in pct_values if value is not None]
        up_count = sum(1 for value in pct_values if value > 0)
        down_count = sum(1 for value in pct_values if value < 0)
        flat_count = max(0, len(pct_values) - up_count - down_count)
        strong_count = sum(1 for value in pct_values if value >= 5)
        weak_count = sum(1 for value in pct_values if value <= -5)
        total_amount = sum(safe_float(row.get("amount")) or 0 for row in bars)
        limit_up_count = sum(1 for row in limit_rows if str(row.get("limit_type") or "").upper().startswith("U"))
        limit_down_count = sum(1 for row in limit_rows if str(row.get("limit_type") or "").upper().startswith("D"))

        index_pcts = [safe_float(row.get("pct_chg")) for row in index_rows]
        index_pcts = [value for value in index_pcts if value is not None]
        index_score = _clamp(50 + (sum(index_pcts) / len(index_pcts)) * 8, 0, 100) if index_pcts else 50
        breadth_score = _clamp(up_count / len(pct_values) * 100, 0, 100) if pct_values else 50
        turnover_score, turnover_ratio = self._market_turnover_score(trade_date, total_amount)
        limit_score = _clamp(50 + (limit_up_count - limit_down_count) / max(len(pct_values), 1) * 100, 0, 100)
        trend_score = round(index_score * 0.35 + breadth_score * 0.35 + turnover_score * 0.15 + limit_score * 0.15, 2)
        risk_level = "risk_on" if trend_score >= 65 else "neutral" if trend_score >= 45 else "risk_off"
        source = "Tushare index_daily + 本地历史宽度" if index_count else "本地历史宽度"
        return {
            "date": trade_date,
            "trend_score": trend_score,
            "risk_level": risk_level,
            "index_score": round(index_score, 2),
            "breadth_score": round(breadth_score, 2),
            "turnover_score": round(turnover_score, 2),
            "limit_score": round(limit_score, 2),
            "up_count": up_count,
            "down_count": down_count,
            "flat_count": flat_count,
            "limit_up_count": limit_up_count,
            "limit_down_count": limit_down_count,
            "strong_count": strong_count,
            "weak_count": weak_count,
            "total_amount": total_amount,
            "source": source,
            "summary_json": {
                "index_codes": [row.get("index_code") for row in index_rows],
                "index_pct_chg": {row.get("index_code"): row.get("pct_chg") for row in index_rows},
                "turnover_ratio": turnover_ratio,
            },
            "updated_at": datetime.utcnow(),
        }

    def _market_turnover_score(self, trade_date: date, total_amount: float) -> tuple[float, Optional[float]]:
        rows = self.db.query(
            """
            SELECT h.date, SUM(h.amount) AS amount
            FROM historical_bars h
            JOIN stock_basic b ON b.code = h.code
            WHERE h.date < ?
              AND h.amount IS NOT NULL
              AND b.suspended IS DISTINCT FROM TRUE
            GROUP BY h.date
            ORDER BY h.date DESC
            LIMIT 20
            """,
            [trade_date],
        )
        amounts = [safe_float(row.get("amount")) for row in rows]
        amounts = [value for value in amounts if value and value > 0]
        if not amounts or not total_amount:
            return 50, None
        average = sum(amounts) / len(amounts)
        ratio = total_amount / average if average else None
        if ratio is None:
            return 50, None
        return _clamp(50 + (ratio - 1) * 35, 0, 100), ratio

    def _fetch_tushare_optional(
        self,
        source_label: str,
        capability: str,
        fetcher: Any,
        warnings: Optional[List[str]],
    ) -> pd.DataFrame:
        attempt = 0
        try:
            while True:
                try:
                    self.tushare_rate_limiter.acquire(_tushare_rate_group(source_label))
                    frame = SourceGuard._call_with_timeout(fetcher, settings.tushare_enrichment_timeout_seconds)
                    if frame is None:
                        frame = pd.DataFrame()
                    self.public_guard.record(
                        source_label,
                        capability,
                        "available",
                        payload={"rows": len(frame), "attempts": attempt + 1},
                    )
                    return frame
                except Exception as exc:
                    message = str(exc)
                    if attempt >= len(TUSHARE_RATE_LIMIT_RETRY_DELAYS) or not _is_tushare_rate_limit_error(message):
                        raise
                    delay = TUSHARE_RATE_LIMIT_RETRY_DELAYS[attempt]
                    attempt += 1
                    logger.info(
                        "Tushare rate limit for %s %s, retrying in %.1fs",
                        source_label,
                        capability,
                        delay,
                    )
                    time.sleep(delay)
        except Exception as exc:
            message = str(exc)
            if warnings is not None:
                warnings.append(f"{source_label} {capability}失败：{message}")
            self.public_guard.record(source_label, capability, "failed", message=message)
            return pd.DataFrame()

    def _persist_tushare_frame(self, table: str, frame: pd.DataFrame, key_columns: List[str]) -> int:
        if frame is None or frame.empty:
            return 0
        columns = TUSHARE_TABLE_COLUMNS[table]
        rows = []
        for item in frame.to_dict("records"):
            item = dict(item)
            if table == "tushare_limit_list_d" and "limit" in item:
                item["limit_type"] = item.pop("limit")
            rows.append({column: item.get(column) for column in columns})
        return self.db.upsert(table, rows, key_columns)

    def _upsert_float_market_values_from_daily_basic(self, frame: pd.DataFrame) -> int:
        if frame is None or frame.empty:
            return 0
        rows = []
        for item in frame.to_dict("records"):
            if not item.get("code") or not item.get("trade_date") or safe_float(item.get("circ_mv")) is None:
                continue
            rows.append(
                {
                    "code": item["code"],
                    "date": item["trade_date"],
                    "float_shares": safe_float(item.get("float_share")),
                    "float_market_value": safe_float(item.get("circ_mv")),
                    "source": "Tushare daily_basic",
                    "updated_at": datetime.utcnow(),
                }
            )
        return self.db.upsert("float_market_values", rows, ["code", "date"])

    def _tushare_codes_missing_for_date(
        self,
        table: str,
        trade_date: date,
        limit: int,
        include_bj: bool,
        exclude_star: bool,
        exclude_codes: Optional[set[str]] = None,
    ) -> List[str]:
        filters = ["b.suspended IS DISTINCT FROM TRUE"]
        params: List[Any] = []
        if not include_bj:
            filters.append("b.code NOT ILIKE '%.BJ'")
        if exclude_star:
            filters.append("b.code NOT LIKE '688%.SH'")
        excluded = sorted(exclude_codes or set())
        if excluded:
            placeholders = ", ".join(["?"] * len(excluded))
            filters.append(f"b.code NOT IN ({placeholders})")
            params.extend(excluded)
        params.append(trade_date)
        sql = f"""
            SELECT b.code
            FROM stock_basic b
            WHERE {' AND '.join(filters)}
              AND NOT EXISTS (
                SELECT 1 FROM {table} t WHERE t.code = b.code AND t.trade_date = ?
              )
            ORDER BY b.code
        """
        if limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        return [row["code"] for row in self.db.query(sql, params)]

    def _tushare_codes_missing_for_member(
        self,
        limit: int,
        include_bj: bool,
        exclude_star: bool,
        exclude_codes: Optional[set[str]] = None,
    ) -> List[str]:
        filters = ["b.suspended IS DISTINCT FROM TRUE"]
        params: List[Any] = []
        if not include_bj:
            filters.append("b.code NOT ILIKE '%.BJ'")
        if exclude_star:
            filters.append("b.code NOT LIKE '688%.SH'")
        excluded = sorted(exclude_codes or set())
        if excluded:
            placeholders = ", ".join(["?"] * len(excluded))
            filters.append(f"b.code NOT IN ({placeholders})")
            params.extend(excluded)
        sql = f"""
            SELECT b.code
            FROM stock_basic b
            WHERE {' AND '.join(filters)}
              AND NOT EXISTS (
                SELECT 1 FROM tushare_ths_member t WHERE t.code = b.code
              )
            ORDER BY b.code
        """
        if limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        return [row["code"] for row in self.db.query(sql, params)]

    def cleanup_intraday_history(
        self,
        retention_days: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, int]:
        keep_days = settings.intraday_retention_days if retention_days is None else retention_days
        if keep_days < 0:
            return {
                "intraday_snapshots": 0,
                "intraday_radar_candidates": 0,
                "intraday_radar_rankings": 0,
            }
        current = now or datetime.now(CHINA_TZ)
        current = current.astimezone(CHINA_TZ).replace(tzinfo=None) if current.tzinfo else current
        cutoff = current.date() - timedelta(days=keep_days)
        deleted: Dict[str, int] = {}
        for table in ["intraday_radar_rankings", "intraday_radar_candidates", "intraday_snapshots"]:
            before = self.db.scalar(f"SELECT COUNT(*) FROM {table}") or 0
            self.db.execute(
                f"""
                DELETE FROM {table}
                WHERE trade_date < ?
                  AND EXISTS (
                    SELECT 1
                    FROM historical_bars h
                    WHERE h.code = {table}.code
                      AND h.date = {table}.trade_date
                  )
                """,
                [cutoff],
                write=True,
            )
            after = self.db.scalar(f"SELECT COUNT(*) FROM {table}") or 0
            deleted[table] = int(before) - int(after)
        return deleted

    def _run_intraday_sample(self, task_id: str, options: Dict[str, Any]) -> None:
        include_bj = bool(options.get("include_bj", settings.include_bj))
        exclude_star = bool(options.get("exclude_star_board", settings.exclude_star_board))
        sample_at = _parse_sample_at(options.get("sample_at")) or datetime.now(CHINA_TZ).replace(tzinfo=None)
        trade_date = sample_at.date()
        warnings: List[str] = []
        try:
            self._patch_task(
                task_id,
                stage="拉取盘中快照",
                source="Tushare 实时日线" if _tushare_realtime_configured() else "AkShare 新浪",
                total=3,
                processed=0,
                success=0,
                failed=0,
                skipped=0,
            )
            frame = self._fetch_intraday_snapshot_frame(include_bj, exclude_star, warnings)
            snapshot_count = self.intraday_service.record_snapshots(
                frame,
                sample_at=sample_at,
                trade_date=trade_date,
            )
            daily_snapshot_count = self._upsert_realtime_daily_snapshots(frame, trade_date)
            market_environment_count = self._update_realtime_market_environment(trade_date)
            sector_heat_count = self._update_realtime_concept_heat(trade_date)
            self._patch_task(
                task_id,
                stage="生成盘中雷达",
                source="本地仓库",
                total=3,
                processed=1,
                success=1 if snapshot_count else 0,
            )
            candidate_count = self.intraday_service.run_radar(sample_at=sample_at)
            radar_result = self.intraday_service.latest(limit=1)
            self._patch_task(
                task_id,
                status="completed_full" if not warnings else "completed_partial",
                stage="盘中雷达完成",
                source="本地仓库",
                total=3,
                processed=3,
                success=1,
                warning=warnings[-1] if warnings else None,
                summary={
                    "snapshot_count": snapshot_count,
                    "daily_snapshot_count": daily_snapshot_count,
                    "market_environment_count": market_environment_count,
                    "sector_heat_count": sector_heat_count,
                    "candidate_count": candidate_count,
                    "strict_count": radar_result.get("summary", {}).get("strict_count", candidate_count),
                    "score_count": radar_result.get("summary", {}).get("score_count", 0),
                    "sample_at": sample_at.isoformat(timespec="seconds"),
                    "warnings": warnings,
                },
                finished_at=datetime.utcnow(),
            )
        except Exception as exc:
            self._patch_task(
                task_id,
                status="failed",
                stage="盘中雷达失败",
                failed=1,
                error_message=str(exc),
                warning=str(exc),
                finished_at=datetime.utcnow(),
            )

    def _run_daily_brief(self, task_id: str, options: Dict[str, Any]) -> None:
        report_date = None
        if options.get("report_date"):
            report_date = date.fromisoformat(str(options["report_date"])[:10])
        try:
            def progress(stage: str, processed: int, total: int) -> None:
                self._patch_task(
                    task_id,
                    stage=stage,
                    source="多源资讯",
                    processed=processed,
                    total=total,
                )

            summary = self.daily_brief_service.generate(report_date=report_date, progress=progress)
            self._patch_task(
                task_id,
                status=summary.get("status") or "completed_partial",
                stage="资讯简报完成",
                source="多源资讯",
                success=1 if summary.get("article_count") else 0,
                failed=0,
                warning=summary.get("visible_warning"),
                summary=summary,
                finished_at=datetime.utcnow(),
            )
        except Exception as exc:
            self._patch_task(
                task_id,
                status="failed",
                stage="资讯简报失败",
                failed=1,
                error_message=str(exc),
                warning=str(exc),
                finished_at=datetime.utcnow(),
            )

    def _fetch_intraday_snapshot_frame(
        self,
        include_bj: bool,
        exclude_star: bool,
        warnings: List[str],
    ) -> pd.DataFrame:
        if _tushare_realtime_configured():
            ts_source = TushareRealtimeSource()
            ts_result = self.public_guard.call(
                "Tushare 实时日线",
                "盘中行情快照",
                lambda: ts_source.fetch_realtime_daily(include_bj=include_bj, exclude_star=exclude_star),
                ttl_minutes=5,
                max_attempts=1,
                timeout_seconds=settings.tushare_timeout_seconds,
            )
            if ts_result.status == "available":
                return ts_result.frame
            if ts_result.message:
                warnings.append(f"Tushare 实时日线失败：{ts_result.message}")

        ak = AkShareSource()
        result = self.public_guard.call(
            "AkShare 新浪",
            "盘中行情快照",
            lambda: ak.fetch_sina_snapshot(include_bj=include_bj, exclude_star=exclude_star),
            ttl_minutes=15,
            max_attempts=2,
            timeout_seconds=120,
        )
        chosen = result
        if result.status != "available":
            warnings.append(f"新浪盘中快照失败：{result.message}")
            chosen = self.public_guard.call(
                "AkShare 腾讯",
                "盘中行情快照",
                lambda: ak.fetch_tencent_snapshot(include_bj=include_bj, exclude_star=exclude_star),
                ttl_minutes=15,
                max_attempts=1,
                timeout_seconds=120,
            )
        if chosen.status != "available":
            if chosen.message:
                warnings.append(f"腾讯盘中快照跳过：{chosen.message}")
        if chosen.status != "available":
            raise RuntimeError(chosen.message or "盘中快照不可用。")
        return chosen.frame

    def _upsert_realtime_daily_snapshots(
        self,
        frame: pd.DataFrame,
        trade_date: Optional[date] = None,
    ) -> int:
        if frame is None or frame.empty:
            return 0
        records = []
        for item in frame.to_dict("records"):
            code = item.get("code")
            if not code:
                continue
            records.append(
                {
                    "code": code,
                    "date": _snapshot_date(item.get("date"), trade_date),
                    "name": item.get("name") or code,
                    "latest_price": safe_float(item.get("latest_price")),
                    "pct_chg": safe_float(item.get("pct_chg")),
                    "high": safe_float(item.get("high")),
                    "low": safe_float(item.get("low")),
                    "volume": safe_float(item.get("volume")),
                    "amount": safe_float(item.get("amount")),
                    "turnover_rate": safe_float(item.get("turnover_rate")),
                    "float_market_value": safe_float(item.get("float_market_value")),
                    "source": item.get("source") or "盘中实时日线",
                    "updated_at": datetime.utcnow(),
                }
            )
        if not records:
            return 0
        count = self.db.upsert("daily_snapshots", records, ["code", "date"])
        self._merge_snapshot_names(pd.DataFrame(records))
        return count

    def _update_basics(
        self,
        force: bool,
        include_bj: bool,
        exclude_star: bool,
        warnings: List[str],
    ) -> int:
        existing = self.db.scalar("SELECT COUNT(*) FROM stock_basic") or 0
        rows_written = 0
        if existing and not force:
            self.public_guard.record(
                "本地缓存",
                "股票基础信息",
                "available",
                payload={"rows": existing, "cache": True},
            )
            return int(existing)
        baostock = BaostockSource()
        try:
            frame = baostock.fetch_stock_basics(include_bj=include_bj, exclude_star=exclude_star)
            rows_written += self.db.upsert("stock_basic", frame.to_dict("records"), ["code"])
            self.baostock_guard.record(
                "Baostock",
                "股票基础信息",
                "available",
                payload={"rows": len(frame)},
            )
        except Exception as exc:
            warnings.append(f"Baostock 股票池失败：{exc}")
            self.baostock_guard.record("Baostock", "股票基础信息", "failed", message=str(exc))

        return rows_written or int(existing)

    def _update_snapshots(
        self,
        force: bool,
        include_bj: bool,
        exclude_star: bool,
        warnings: List[str],
    ) -> int:
        today_rows = self.db.scalar(
            "SELECT COUNT(*) FROM daily_snapshots WHERE date = current_date"
        ) or 0
        if today_rows and not force:
            self.public_guard.record(
                "本地缓存",
                "当天行情快照",
                "available",
                payload={"rows": today_rows, "cache": True},
            )
            return int(today_rows)
        if _tushare_realtime_configured():
            ts_source = TushareRealtimeSource()
            ts_result = self.public_guard.call(
                "Tushare 实时日线",
                "当天行情快照",
                lambda: ts_source.fetch_realtime_daily(include_bj=include_bj, exclude_star=exclude_star),
                ttl_minutes=5,
                max_attempts=1,
                timeout_seconds=settings.tushare_timeout_seconds,
            )
            if ts_result.status == "available":
                return self._upsert_realtime_daily_snapshots(ts_result.frame)
            if ts_result.message:
                warnings.append(f"Tushare 实时日线快照失败：{ts_result.message}")
        ak = AkShareSource()
        result = self.public_guard.call(
            "AkShare 新浪",
            "当天行情快照",
            lambda: ak.fetch_sina_snapshot(include_bj=include_bj, exclude_star=exclude_star),
            ttl_minutes=settings.source_probe_ttl_minutes,
            max_attempts=2,
        )
        chosen = result
        if result.status != "available":
            warnings.append(f"新浪快照失败：{result.message}")
            chosen = self.public_guard.call(
                "AkShare 腾讯",
                "当天行情快照",
                lambda: ak.fetch_tencent_snapshot(include_bj=include_bj, exclude_star=exclude_star),
                ttl_minutes=settings.source_probe_ttl_minutes,
                max_attempts=1,
            )
        if chosen.status != "available":
            if chosen.message:
                warnings.append(f"腾讯快照跳过：{chosen.message}")
        if chosen.status == "available":
            records = chosen.frame.to_dict("records")
            count = self.db.upsert("daily_snapshots", records, ["code", "date"])
            self._merge_snapshot_names(chosen.frame)
            return count
        if chosen.message:
            warnings.append(f"快照全部降级到本地缓存：{chosen.message}")
        return int(today_rows)

    def _history_stocks_for_update(
        self,
        limit: int,
        light: bool,
        target_history_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        if not light:
            return self.db.query(
                """
                SELECT b.code
                FROM stock_basic b
                WHERE b.suspended IS DISTINCT FROM TRUE
                ORDER BY b.code
                """ + (" LIMIT ?" if limit else ""),
                [limit] if limit else [],
            )

        target = target_history_date or self._target_history_date()
        sql = """
            SELECT code, latest_history_date
            FROM (
                SELECT b.code, MAX(h.date) AS latest_history_date
                FROM stock_basic b
                INNER JOIN daily_snapshots s
                   ON s.code = b.code
                  AND s.date = (SELECT MAX(date) FROM daily_snapshots)
                LEFT JOIN historical_bars h ON h.code = b.code
                WHERE b.suspended IS DISTINCT FROM TRUE
                GROUP BY b.code
            )
            WHERE latest_history_date IS NULL OR latest_history_date < ?
            ORDER BY code
        """
        params: List[Any] = [target]
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        return self.db.query(sql, params)

    def _history_stocks_missing_for_target(
        self,
        target: date,
        include_bj: bool,
        exclude_star: bool,
        limit: int = 0,
    ) -> List[Dict[str, Any]]:
        filters = ["b.suspended IS DISTINCT FROM TRUE"]
        params: List[Any] = [target]
        if not include_bj:
            filters.append("b.code NOT ILIKE '%.BJ'")
        if exclude_star:
            filters.append("b.code NOT LIKE '688%.SH'")
        sql = f"""
            SELECT b.code, MAX(h.date) AS latest_history_date
            FROM stock_basic b
            LEFT JOIN historical_bars h ON h.code = b.code
            WHERE {' AND '.join(filters)}
            GROUP BY b.code
            HAVING latest_history_date IS NULL OR latest_history_date < ?
            ORDER BY b.code
        """
        if limit > 0:
            sql += " LIMIT ?"
            params.append(limit)
        return self.db.query(sql, params)

    def _update_history(
        self,
        stocks: List[Dict[str, Any]],
        start: date,
        end: date,
        force: bool,
        task_id: str,
        incremental: bool = False,
        target_history_date: Optional[date] = None,
    ) -> tuple:
        if _tushare_history_configured():
            try:
                return self._update_tushare_history(stocks, start, end, task_id)
            except Exception as exc:
                self.public_guard.record(
                    "Tushare daily 前复权",
                    "历史 K 线",
                    "failed",
                    message=str(exc),
                    ttl_minutes=15,
                )
                self._patch_task(
                    task_id,
                    source="Baostock",
                    warning=f"Tushare 历史 K 线失败，回退 Baostock：{exc}",
                )

        baostock = BaostockSource()
        success = 0
        failed = 0
        skipped = 0
        total = len(stocks)
        target = target_history_date or self._target_history_date()
        for index, row in enumerate(stocks, start=1):
            code = row["code"]
            latest = row.get("latest_history_date")
            if latest is None:
                latest = self.db.scalar("SELECT MAX(date) FROM historical_bars WHERE code = ?", [code])
            if incremental and latest and not force and str(latest) >= target.isoformat():
                skipped += 1
                self._patch_task(
                    task_id,
                    current_stock=code,
                    processed=index,
                    skipped=skipped,
                    success=success,
                    failed=failed,
                )
                continue
            fetch_start = self._history_fetch_start(start, latest, incremental=incremental)
            if incremental and fetch_start > end:
                skipped += 1
                self._patch_task(
                    task_id,
                    current_stock=code,
                    processed=index,
                    skipped=skipped,
                    success=success,
                    failed=failed,
                )
                continue
            try:
                self.baostock_guard.sleep()
                frame = baostock.fetch_history(code, fetch_start, end)
                if frame.empty:
                    raise RuntimeError("Baostock 历史行情为空")
                self.db.upsert("historical_bars", frame.to_dict("records"), ["code", "date"])
                success += 1
            except Exception as exc:
                failed += 1
                self.baostock_guard.record(
                    "Baostock",
                    "历史 K 线",
                    "failed",
                    message=f"{code}: {exc}",
                    ttl_minutes=15,
                )
            self._patch_task(
                task_id,
                current_stock=code,
                total=total,
                processed=index,
                success=success,
                failed=failed,
                skipped=skipped,
            )
        if success:
            self.baostock_guard.record(
                "Baostock",
                "历史 K 线",
                "available",
                payload={"success": success, "failed": failed, "skipped": skipped},
            )
        return success, failed, skipped

    def _update_tushare_history(
        self,
        stocks: List[Dict[str, Any]],
        start: date,
        end: date,
        task_id: str,
    ) -> tuple:
        if not stocks:
            return 0, 0, 0

        codes = [str(row["code"]) for row in stocks if row.get("code")]
        total = len(codes)
        if not codes:
            return 0, 0, 0

        source = TushareEnrichmentSource()
        history_days = [day for day in _date_span(start, end) if day.weekday() < 5]
        day_total = len(history_days)
        if not history_days:
            return 0, 0, total
        latest_history_day = history_days[-1]

        self._patch_tushare_history_progress(
            task_id,
            day=history_days[0],
            day_index=0,
            day_total=day_total,
            step="准备参考因子",
            processed=0,
            total_written_rows=0,
        )
        reference_factors, reference_date = source.fetch_history_reference_factors(end, codes=codes)
        if not reference_factors:
            raise RuntimeError("Tushare 历史 K 线参考复权因子为空")

        st_rows = self.db.query("SELECT code, is_st FROM stock_basic")
        is_st_by_code = {str(row["code"]): bool(row.get("is_st")) for row in st_rows}
        total_written_rows = 0
        skipped_days = 0
        success_codes = set()

        for day_index, day in enumerate(history_days, start=1):
            def progress(step: str) -> None:
                self._patch_tushare_history_progress(
                    task_id,
                    day=day,
                    day_index=day_index,
                    day_total=day_total,
                    step=step,
                    processed=day_index - 1,
                    total_written_rows=total_written_rows,
                    reference_date=reference_date,
                )

            frame = source.fetch_history_day(day, reference_factors, codes=codes, progress=progress)
            if frame is None or frame.empty:
                skipped_days += 1
                self._patch_tushare_history_progress(
                    task_id,
                    day=day,
                    day_index=day_index,
                    day_total=day_total,
                    step="空日",
                    processed=day_index,
                    total_written_rows=total_written_rows,
                    reference_date=reference_date,
                )
                continue

            rows = []
            for item in frame.to_dict("records"):
                row = dict(item)
                code = str(row.get("code") or "")
                if row.get("is_st") is None:
                    row["is_st"] = is_st_by_code.get(code, False)
                rows.append(row)

            self.db.upsert("historical_bars", rows, ["code", "date"])
            total_written_rows += len(rows)
            if day == latest_history_day:
                success_codes.update(str(row["code"]) for row in rows if row.get("code"))

            if day_index % 10 == 0 or day == latest_history_day:
                logger.info(
                    "Tushare history qfq progress %s/%s date=%s wrote=%s total_rows=%s",
                    day_index,
                    day_total,
                    day.isoformat(),
                    len(rows),
                    total_written_rows,
                )

            self._patch_tushare_history_progress(
                task_id,
                day=day,
                day_index=day_index,
                day_total=day_total,
                step="写入",
                processed=day_index,
                total_written_rows=total_written_rows,
                reference_date=reference_date,
            )

        success = len(success_codes)
        skipped = max(0, total - success)
        self.public_guard.record(
            "Tushare daily 前复权",
            "历史 K 线",
            "available",
            payload={
                "success": success,
                "skipped": skipped,
                "skipped_days": skipped_days,
                "rows": total_written_rows,
                "reference_date": reference_date,
            },
        )
        self._patch_tushare_history_progress(
            task_id,
            day=latest_history_day,
            day_index=day_total,
            day_total=day_total,
            step="完成",
            processed=day_total,
            total_written_rows=total_written_rows,
            reference_date=reference_date,
            success=success,
            skipped=skipped,
        )
        return success, 0, skipped

    def _patch_tushare_history_progress(
        self,
        task_id: str,
        day: date,
        day_index: int,
        day_total: int,
        step: str,
        processed: int,
        total_written_rows: int,
        reference_date: Optional[str] = None,
        success: int = 0,
        skipped: int = 0,
    ) -> None:
        summary = {
            "history_progress": {
                "mode": "streaming",
                "current_date": day.isoformat(),
                "step": step,
                "day_index": day_index,
                "day_total": day_total,
                "written_rows": total_written_rows,
                "reference_date": reference_date,
                "last_heartbeat_at": datetime.utcnow().isoformat(timespec="seconds"),
            }
        }
        self._patch_task(
            task_id,
            source="Tushare daily 前复权",
            current_stock=f"{day.isoformat()} · {step}",
            total=day_total,
            processed=processed,
            success=success,
            failed=0,
            skipped=skipped,
            summary=summary,
        )

    @staticmethod
    def _target_history_date(now: Optional[datetime] = None) -> date:
        current = now or datetime.now(CHINA_TZ)
        if current.tzinfo is not None:
            current = current.astimezone(CHINA_TZ).replace(tzinfo=None)
        current_day = current.date()
        if current.weekday() < 5 and current.hour >= HISTORY_CLOSE_HOUR:
            return current_day
        return UpdateService._previous_weekday(current_day)

    @staticmethod
    def _previous_weekday(day: date) -> date:
        target = day - timedelta(days=1)
        while target.weekday() >= 5:
            target -= timedelta(days=1)
        return target

    @staticmethod
    def _history_fetch_start(default_start: date, latest: Any, incremental: bool) -> date:
        if not incremental or not latest:
            return default_start
        if isinstance(latest, datetime):
            latest_date = latest.date()
        elif isinstance(latest, date):
            latest_date = latest
        else:
            latest_date = date.fromisoformat(str(latest)[:10])
        return latest_date + timedelta(days=1)

    def _update_float_values_from_snapshots(self) -> int:
        snapshots = self.db.query(
            """
            SELECT code, date, latest_price, float_market_value, source
            FROM daily_snapshots
            WHERE date = (SELECT MAX(date) FROM daily_snapshots)
            """
        )
        history_rows = self.db.query(
            """
            SELECT code, volume, turn
            FROM (
                SELECT code,
                       volume,
                       turn,
                       ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rank
                FROM historical_bars
                WHERE date <= (SELECT MAX(date) FROM daily_snapshots)
                  AND volume IS NOT NULL
                  AND volume > 0
                  AND turn IS NOT NULL
                  AND turn > 0
            )
            WHERE rank = 1
            """
        )
        history_by_code = {row["code"]: row for row in history_rows}
        rows = []
        for item in snapshots:
            latest = safe_float(item.get("latest_price"))
            float_mv = safe_float(item.get("float_market_value"))
            source = item.get("source") or "本地缓存"
            float_shares = float_mv / latest if latest and latest > 0 and float_mv else None
            if float_mv is None and latest and latest > 0:
                history = history_by_code.get(item["code"])
                volume = safe_float((history or {}).get("volume"))
                turn = safe_float((history or {}).get("turn"))
                if volume and volume > 0 and turn and turn > 0:
                    float_shares = volume / (turn / 100)
                    float_mv = float_shares * latest
                    source = "Baostock 换手率估算"
            if float_mv is None:
                continue
            rows.append(
                {
                    "code": item["code"],
                    "date": item["date"],
                    "float_shares": float_shares,
                    "float_market_value": float_mv,
                    "source": source,
                    "updated_at": datetime.utcnow(),
                }
            )
        count = self.db.upsert("float_market_values", rows, ["code", "date"])
        estimated_count = sum(1 for row in rows if row["source"] == "Baostock 换手率估算")
        direct_count = count - estimated_count
        if direct_count:
            self.public_guard.record(
                "AkShare 新浪",
                "流通市值",
                "available",
                payload={"rows": direct_count, "method": "snapshot_float_market_value"},
            )
        if estimated_count:
            self.baostock_guard.record(
                "Baostock",
                "流通市值",
                "available",
                payload={"rows": estimated_count, "method": "turnover_implied_float_market_value"},
            )
        if not count:
            self.public_guard.record(
                "本地缓存",
                "流通市值",
                "available",
                payload={"rows": 0, "cache": True},
            )
        return count

    def _merge_basic_names(self, frame: pd.DataFrame) -> int:
        if frame.empty:
            return 0
        existing_rows = self.db.query("SELECT code, name FROM stock_basic")
        existing = {row["code"]: row.get("name") for row in existing_rows}
        rows = []
        name_updates = []
        for item in frame.to_dict("records"):
            if item["code"] in existing:
                if item.get("name") and not existing[item["code"]]:
                    name_updates.append(item)
            else:
                rows.append(item)
        if name_updates:
            for item in name_updates:
                self.db.execute(
                    "UPDATE stock_basic SET name = ?, updated_at = ? WHERE code = ?",
                    [item["name"], datetime.utcnow(), item["code"]],
                    write=True,
                )
        inserted = self.db.upsert("stock_basic", rows, ["code"]) if rows else 0
        return inserted + len(name_updates)

    def _merge_snapshot_names(self, frame: pd.DataFrame) -> None:
        for item in frame.to_dict("records"):
            if item.get("name"):
                self.db.execute(
                    """
                    UPDATE stock_basic
                    SET name = COALESCE(NULLIF(name, ''), ?), updated_at = ?
                    WHERE code = ?
                    """,
                    [item["name"], datetime.utcnow(), item["code"]],
                    write=True,
                )

    def _write_task(self, task_id: str, **values: Any) -> None:
        now = datetime.utcnow()
        row = {
            "id": task_id,
            "kind": values.get("kind"),
            "status": values.get("status"),
            "stage": values.get("stage"),
            "source": values.get("source"),
            "current_stock": values.get("current_stock"),
            "total": values.get("total", 0),
            "processed": values.get("processed", 0),
            "success": values.get("success", 0),
            "failed": values.get("failed", 0),
            "skipped": values.get("skipped", 0),
            "warning": values.get("warning"),
            "summary_json": json.dumps(values.get("summary") or {}, ensure_ascii=False),
            "payload_json": json.dumps(values.get("payload") or {}, ensure_ascii=False),
            "queue_order": values.get("queue_order") or (time.time_ns() if values.get("status") == "queued" else None),
            "cancel_requested": False,
            "started_at": values.get("started_at") or now,
            "updated_at": now,
            "finished_at": values.get("finished_at"),
            "error_message": values.get("error_message"),
        }
        self.db.upsert("task_runs", [row], ["id"])

    def _patch_task(self, task_id: str, **changes: Any) -> None:
        current = self.db.query("SELECT * FROM task_runs WHERE id = ?", [task_id])
        if not current:
            return
        row = current[0]
        summary = changes.pop("summary", None)
        if summary is not None:
            changes["summary_json"] = json.dumps(summary, ensure_ascii=False)
        changes["updated_at"] = datetime.utcnow()
        merged = {**row, **changes}
        self.db.upsert("task_runs", [merged], ["id"])


def _parse_sample_at(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace(" ", "T")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is not None:
        return parsed.astimezone(CHINA_TZ).replace(tzinfo=None)
    return parsed


def _date_span(start: date, end: date) -> List[date]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def _date_option(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return max(1, parsed)


def _is_tushare_rate_limit_error(message: str) -> bool:
    text = (message or "").lower()
    return any(
        marker in text
        for marker in [
            "请求速度过快",
            "请求过快",
            "请求频率",
            "too many",
            "rate limit",
            "ratelimit",
            "429",
        ]
    )


def _tushare_rate_group(source_label: str) -> str:
    text = (source_label or "").lower()
    if "realtime" in text or "实时" in source_label:
        return "realtime"
    if "daily_basic" in text:
        return "daily_basic"
    if "stk_factor" in text:
        return "stk_factor"
    if "moneyflow" in text:
        return "moneyflow"
    if "cyq" in text:
        return "cyq"
    if "top" in text or "hm_detail" in text or "龙虎" in source_label:
        return "top"
    if "ths" in text or "板块" in source_label or "概念" in source_label:
        return "ths"
    return "daily_basic"
