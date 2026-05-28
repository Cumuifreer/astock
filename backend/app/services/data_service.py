from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from backend.app.db import Database
from backend.app.services.intraday_schedule import parse_intraday_schedule
from backend.app.services.market_utils import safe_float


CHINA_TZ = ZoneInfo("Asia/Shanghai")


STOCK_BOARD_CASE = """
CASE
    WHEN b.exchange = 'BJ' OR b.code ILIKE '%.BJ' THEN 'bj'
    WHEN b.exchange = 'SH' AND (b.code LIKE '688%' OR b.code LIKE '689%') THEN 'star'
    WHEN b.exchange = 'SZ' AND (b.code LIKE '300%' OR b.code LIKE '301%') THEN 'gem'
    WHEN b.exchange = 'SH' AND b.code LIKE '60%' THEN 'main'
    WHEN b.exchange = 'SZ' AND b.code LIKE '00%' THEN 'main'
    ELSE 'other'
END
"""

LOCAL_VOLUME_RATIO_JOIN = """
LEFT JOIN (
    SELECT code,
           CASE
               WHEN base_volume > 0 THEN latest_volume / base_volume
               ELSE NULL
           END AS local_volume_ratio
    FROM (
        SELECT code,
               MAX(CASE WHEN rn = 1 THEN volume END) AS latest_volume,
               AVG(CASE WHEN rn > 1 THEN volume END) AS base_volume
        FROM (
            SELECT code,
                   volume,
                   ROW_NUMBER() OVER (PARTITION BY code ORDER BY date DESC) AS rn
            FROM historical_bars
            WHERE volume IS NOT NULL
        ) ranked
        WHERE rn <= 21
        GROUP BY code
    ) volume_base
) hv ON hv.code = b.code
"""

ACTIVE_STOCK_FILTER = "b.suspended IS DISTINCT FROM TRUE"
INACTIVE_STOCK_FILTER = "b.suspended IS TRUE"


def _is_blocked_brief_source(item: Dict[str, Any]) -> bool:
    source_text = f"{item.get('source_id') or ''} {item.get('source') or ''}".lower()
    return (
        "36kr" in source_text
        or "36氪" in source_text
        or "github-trending" in source_text
        or "github trending" in source_text
    )


def _brief_article_sort_key(item: Dict[str, Any]) -> datetime:
    value = item.get("published_at")
    if isinstance(value, datetime):
        return value
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.min


def _format_brief_published(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value or "")


CAPABILITY_DEFINITIONS = {
    "历史 K 线": {
        "fallback_sources": ["Tushare daily 前复权", "Baostock", "本地缓存"],
        "can_backfill": True,
        "participates_in_analysis": True,
        "coverage_kind": "stock",
    },
    "当天行情快照": {
        "fallback_sources": ["Tushare 实时日线", "AkShare 新浪", "AkShare 腾讯", "本地缓存"],
        "can_backfill": True,
        "participates_in_analysis": True,
        "coverage_kind": "stock",
    },
    "股票基础信息": {
        "fallback_sources": ["Baostock", "AkShare 快照", "本地缓存"],
        "can_backfill": True,
        "participates_in_analysis": True,
        "coverage_kind": "stock",
    },
    "流通市值": {
        "fallback_sources": ["Tushare daily_basic", "AkShare 新浪", "本地缓存"],
        "can_backfill": True,
        "participates_in_analysis": True,
        "coverage_kind": "stock",
    },
    "换手率": {
        "fallback_sources": ["Tushare daily_basic", "Baostock", "AkShare 新浪", "本地缓存"],
        "can_backfill": True,
        "participates_in_analysis": True,
        "coverage_kind": "stock",
    },
    "RPS": {
        "fallback_sources": ["本地历史 K 线"],
        "can_backfill": True,
        "participates_in_analysis": True,
        "coverage_kind": "stock",
    },
    "振幅": {
        "fallback_sources": ["本地历史 K 线"],
        "can_backfill": True,
        "participates_in_analysis": True,
        "coverage_kind": "stock",
    },
    "ST / 停牌状态": {
        "fallback_sources": ["股票基础信息", "Tushare 日线缺行", "Baostock", "本地缓存"],
        "can_backfill": True,
        "participates_in_analysis": True,
        "coverage_kind": "stock",
    },
    "市场环境": {
        "fallback_sources": ["Tushare index_daily", "本地历史宽度", "Tushare limit_list_d"],
        "can_backfill": True,
        "participates_in_analysis": False,
        "coverage_kind": "dataset",
    },
    "每日指标": {
        "fallback_sources": ["Tushare daily_basic"],
        "can_backfill": True,
        "participates_in_analysis": True,
        "coverage_kind": "stock",
    },
    "技术因子": {
        "fallback_sources": ["Tushare stk_factor"],
        "can_backfill": True,
        "participates_in_analysis": True,
        "coverage_kind": "stock",
    },
    "资金流向": {
        "fallback_sources": ["Tushare moneyflow"],
        "can_backfill": True,
        "participates_in_analysis": False,
        "coverage_kind": "stock",
    },
    "涨跌停": {
        "fallback_sources": ["Tushare limit_list_d"],
        "can_backfill": True,
        "participates_in_analysis": False,
        "coverage_kind": "event",
    },
    "筹码分布": {
        "fallback_sources": ["Tushare cyq_perf", "Tushare cyq_chips"],
        "can_backfill": True,
        "participates_in_analysis": False,
        "coverage_kind": "stock",
    },
    "概念/行业成分": {
        "fallback_sources": ["Tushare ths_member"],
        "can_backfill": True,
        "participates_in_analysis": False,
        "coverage_kind": "stock",
    },
    "板块热力": {
        "fallback_sources": ["Tushare moneyflow_cnt_ths", "Tushare moneyflow_ind_ths", "Tushare ths_daily"],
        "can_backfill": True,
        "participates_in_analysis": False,
        "coverage_kind": "dataset",
    },
    "龙虎榜/游资": {
        "fallback_sources": ["Tushare top_list", "Tushare top_inst", "Tushare hm_detail"],
        "can_backfill": True,
        "participates_in_analysis": False,
        "coverage_kind": "event",
    },
}

DATA_UPDATE_DAG: List[Dict[str, Any]] = [
    {"id": "stock_basic", "label": "股票基础信息", "capability": "股票基础信息", "dependencies": [], "freshness_policy": "long_lived"},
    {"id": "daily_snapshot", "label": "实时日线 / 当日快照", "capability": "当天行情快照", "dependencies": ["stock_basic"], "freshness_policy": "intraday"},
    {"id": "history_qfq", "label": "历史前复权 K 线", "capability": "历史 K 线", "dependencies": ["daily_snapshot"], "freshness_policy": "daily"},
    {"id": "daily_basic", "label": "每日指标", "capability": "每日指标", "dependencies": ["history_qfq"], "freshness_policy": "daily"},
    {"id": "stk_factor", "label": "技术因子", "capability": "技术因子", "dependencies": ["history_qfq"], "freshness_policy": "daily"},
    {"id": "moneyflow", "label": "资金流向", "capability": "资金流向", "dependencies": ["history_qfq"], "freshness_policy": "daily"},
    {"id": "limit_list_d", "label": "涨跌停事件", "capability": "涨跌停", "dependencies": ["history_qfq"], "freshness_policy": "event"},
    {"id": "cyq_perf", "label": "筹码表现", "capability": "筹码分布", "dependencies": ["history_qfq"], "freshness_policy": "daily"},
    {"id": "cyq_chips", "label": "筹码价格分布", "capability": "筹码分布", "dependencies": ["history_qfq"], "freshness_policy": "daily"},
    {"id": "ths_member", "label": "题材成分", "capability": "概念/行业成分", "dependencies": ["stock_basic"], "freshness_policy": "long_lived"},
    {"id": "board_moneyflow", "label": "板块热力 / 资金", "capability": "板块热力", "dependencies": ["ths_member", "history_qfq"], "freshness_policy": "daily"},
    {"id": "top_list", "label": "龙虎榜", "capability": "龙虎榜/游资", "dependencies": ["history_qfq"], "freshness_policy": "event"},
    {"id": "top_inst", "label": "机构席位", "capability": "龙虎榜/游资", "dependencies": ["history_qfq"], "freshness_policy": "event"},
    {"id": "hm_detail", "label": "游资明细", "capability": "龙虎榜/游资", "dependencies": ["history_qfq"], "freshness_policy": "event"},
    {"id": "market_environment", "label": "市场环境", "capability": "市场环境", "dependencies": ["daily_basic", "moneyflow", "limit_list_d", "board_moneyflow"], "freshness_policy": "daily"},
    {"id": "capability_refresh", "label": "能力口径刷新", "capability": "数据能力", "dependencies": ["market_environment"], "freshness_policy": "manual"},
]

DAG_TERMINAL_TASK_STATUSES = {"completed_full", "completed_partial", "failed", "skipped"}
DAG_BLOCKING_CHECKPOINT_STATUSES = {"failed", "blocked"}


def _slot_status(
    current: datetime,
    slot: datetime,
    task: Optional[Dict[str, Any]],
    scheduler_enabled: bool,
    catchup_minutes: int,
) -> str:
    if not scheduler_enabled:
        return "disabled"
    if current.weekday() >= 5:
        return "weekend"
    if task:
        return str(task.get("status") or "queued")
    if current < slot:
        return "pending"
    if slot <= current < slot + timedelta(minutes=catchup_minutes):
        return "due"
    return "missed"


def _diagnostic_status(
    row: Dict[str, Any],
    fallback_source: Optional[str],
    expected_source: str,
) -> str:
    status = str(row.get("status") or "")
    if status in {"available", "completed_full", "completed_partial"}:
        return "normal"
    if status in {"failed", "unavailable"}:
        return "failed"
    if fallback_source and expected_source not in str(fallback_source):
        return "fallback"
    return "unknown"


def _aggregate_diagnostic_status(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return "unknown"
    statuses = {str(row.get("status") or "") for row in rows}
    if statuses <= {"available", "completed_full", "completed_partial"}:
        return "normal"
    if statuses & {"available", "completed_full", "completed_partial"}:
        return "partial"
    if statuses & {"failed", "unavailable"}:
        return "failed"
    return "unknown"


def _latest_scheduled_task_slot(tasks_by_id: Dict[str, Dict[str, Any]]) -> Optional[datetime]:
    slots: List[datetime] = []
    for task_id in tasks_by_id:
        try:
            _, _, yyyymmdd, hhmm = task_id.split("-", 3)
            slots.append(datetime.strptime(f"{yyyymmdd}{hhmm}", "%Y%m%d%H%M").replace(tzinfo=CHINA_TZ))
        except ValueError:
            continue
    return max(slots) if slots else None


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


class DataService:
    def __init__(self, db: Database):
        self.db = db

    def active_stock_count(self) -> int:
        return int(
            self.db.scalar(
                f"SELECT COUNT(*) FROM stock_basic b WHERE {ACTIVE_STOCK_FILTER}"
            )
            or 0
        )

    def inactive_stock_count(self) -> int:
        return int(
            self.db.scalar(
                f"SELECT COUNT(*) FROM stock_basic b WHERE {INACTIVE_STOCK_FILTER}"
            )
            or 0
        )

    def overview(self) -> Dict[str, Any]:
        latest_run = self.latest_analysis_run()
        latest_task = self.latest_task("update")
        latest_brief = self.latest_daily_brief()
        stock_count = self.db.scalar("SELECT COUNT(*) FROM stock_basic") or 0
        active_stock_count = self.active_stock_count()
        inactive_stock_count = self.inactive_stock_count()
        return {
            "stock_count": stock_count,
            "active_stock_count": active_stock_count,
            "inactive_stock_count": inactive_stock_count,
            "history_rows": self.db.scalar("SELECT COUNT(*) FROM historical_bars") or 0,
            "snapshot_rows": self.db.scalar("SELECT COUNT(*) FROM daily_snapshots") or 0,
            "latest_history_date": self.db.scalar("SELECT MAX(date) FROM historical_bars"),
            "latest_snapshot_date": self.db.scalar("SELECT MAX(date) FROM daily_snapshots"),
            "turnover_coverage": self._ratio(
                self.db.scalar(
                    f"""
                    SELECT COUNT(DISTINCT h.code)
                    FROM historical_bars h
                    JOIN stock_basic b ON b.code = h.code
                    WHERE h.turn IS NOT NULL
                      AND h.date = (SELECT MAX(date) FROM historical_bars)
                      AND {ACTIVE_STOCK_FILTER}
                    """
                )
                or 0,
                active_stock_count,
            ),
            "latest_analysis": latest_run,
            "latest_update": latest_task,
            "latest_brief": latest_brief,
            "warnings": self.db.query(
                "SELECT * FROM warnings ORDER BY created_at DESC LIMIT 8"
            ),
        }

    def market_overview(self) -> Dict[str, Any]:
        environment = self._latest_market_environment()
        trade_date = environment.get("date") if environment else self.db.scalar("SELECT MAX(date) FROM historical_bars")
        sector_nodes = self.sector_heatmap("concept", limit=40)
        state = self._market_state(environment, sector_nodes)
        pulse = {
            "breadth_score": _round(environment.get("breadth_score") if environment else None),
            "index_score": _round(environment.get("index_score") if environment else None),
            "turnover_score": _round(environment.get("turnover_score") if environment else None),
            "limit_score": _round(environment.get("limit_score") if environment else None),
            "sector_heat_score": _round(_avg_value(sector_nodes[:10], "heat_score")),
            "up_count": environment.get("up_count") if environment else 0,
            "down_count": environment.get("down_count") if environment else 0,
            "limit_up_count": environment.get("limit_up_count") if environment else 0,
            "limit_down_count": environment.get("limit_down_count") if environment else 0,
            "total_amount": environment.get("total_amount") if environment else None,
        }
        return {
            "trade_date": trade_date,
            "state": state,
            "pulse": pulse,
            "sector_heatmap": sector_nodes,
            "action_items": self._daily_action_items(state, sector_nodes),
            "data_freshness": self._data_freshness(),
        }

    def sector_heatmap(self, sector_type: str = "concept", metric: str = "heat", limit: int = 80) -> List[Dict[str, Any]]:
        resolved_type = "industry" if str(sector_type).lower() == "industry" else "concept"
        order_column = {
            "pct_chg": "pct_chg",
            "moneyflow": "net_amount",
            "limit": "limit_up_count",
            "heat": "heat_score",
        }.get(str(metric).lower(), "heat_score")
        rows = self.db.query(
            f"""
            SELECT sector_code AS code,
                   sector_name AS name,
                   sector_type AS type,
                   trade_date,
                   pct_chg,
                   amount,
                   net_amount,
                   company_count,
                   COALESCE(limit_up_count, 0) AS limit_up_count,
                   COALESCE(strong_count, 0) AS strong_count,
                   leader_code,
                   leader_name,
                   heat_score,
                   source,
                   updated_at
            FROM market_sector_daily
            WHERE sector_type = ?
              AND trade_date = (
                SELECT MAX(trade_date)
                FROM market_sector_daily
                WHERE sector_type = ?
              )
            ORDER BY {order_column} DESC NULLS LAST, sector_name
            LIMIT ?
            """,
            [resolved_type, resolved_type, max(1, min(limit, 300))],
        )
        return rows

    def task_checkpoints(self, task_id: str) -> List[Dict[str, Any]]:
        rows = self.db.query(
            """
            SELECT *
            FROM update_checkpoints
            WHERE task_id = ?
            ORDER BY started_at, job_id, batch_key
            """,
            [task_id],
        )
        dag_order = {node["id"]: index for index, node in enumerate(DATA_UPDATE_DAG)}
        rows.sort(
            key=lambda row: (
                row.get("started_at") or datetime.min,
                dag_order.get(str(row.get("job_id") or ""), 10_000),
                str(row.get("job_id") or ""),
                str(row.get("batch_key") or ""),
            )
        )
        for row in rows:
            row["payload"] = json.loads(row.pop("payload_json") or "{}")
        return rows

    def task_dag(self, task_id: str) -> Dict[str, Any]:
        checkpoints = self.task_checkpoints(task_id)
        by_job = {row["job_id"]: row for row in checkpoints}
        task_status = self.db.scalar("SELECT status FROM task_runs WHERE id = ?", [task_id])
        task_is_terminal = str(task_status or "") in DAG_TERMINAL_TASK_STATUSES
        status_by_id: Dict[str, str] = {}
        nodes = []
        for node in DATA_UPDATE_DAG:
            checkpoint = by_job.get(node["id"])
            dependencies = node.get("dependencies") or []
            if checkpoint:
                status = str(checkpoint.get("status") or "queued")
            elif any(status_by_id.get(dep) in DAG_BLOCKING_CHECKPOINT_STATUSES for dep in dependencies):
                status = "blocked"
            elif task_is_terminal:
                status = "not_reached"
            else:
                status = "queued"
            status_by_id[node["id"]] = status
            nodes.append(
                {
                    **node,
                    "status": status,
                    "target_date": checkpoint.get("target_date") if checkpoint else None,
                    "rows_written": checkpoint.get("rows_written") if checkpoint else 0,
                    "reason": (checkpoint.get("payload") or {}).get("reason") if checkpoint else None,
                }
            )
        return {"task_id": task_id, "nodes": nodes}

    def source_diagnostics(self) -> Dict[str, Any]:
        from backend.app.config import settings

        status_rows = self.db.query(
            """
            SELECT source, capability, status, last_checked, last_success, last_failure, failure_reason, payload_json
            FROM source_status
            ORDER BY last_checked DESC NULLS LAST
            """
        )
        latest_by_source_cap: Dict[str, Dict[str, Any]] = {}
        for row in status_rows:
            key = f"{row.get('source')}::{row.get('capability')}"
            if key not in latest_by_source_cap:
                decoded = dict(row)
                decoded["payload"] = json.loads(decoded.pop("payload_json") or "{}")
                latest_by_source_cap[key] = decoded

        tushare_rows = [
            row
            for row in latest_by_source_cap.values()
            if "tushare" in str(row.get("source") or "").lower()
        ]
        tushare_failures = [
            row
            for row in tushare_rows
            if row.get("failure_reason") or row.get("status") in {"failed", "unavailable"}
        ]
        snapshot_source = self.db.scalar(
            """
            SELECT source
            FROM daily_snapshots
            ORDER BY updated_at DESC NULLS LAST, date DESC NULLS LAST
            LIMIT 1
            """
        )
        history_source = self.db.scalar(
            """
            SELECT source
            FROM historical_bars
            ORDER BY updated_at DESC NULLS LAST, date DESC NULLS LAST
            LIMIT 1
            """
        )

        def status_for(source: str, capability: str) -> Dict[str, Any]:
            return latest_by_source_cap.get(f"{source}::{capability}", {})

        realtime_status = status_for("Tushare 实时日线", "当天行情快照") or status_for("Tushare 实时日线", "盘中行情快照")
        history_status = status_for("Tushare daily 前复权", "历史 K 线")
        enrichment_statuses = [
            row
            for row in tushare_rows
            if row.get("capability") in {"每日指标", "技术因子", "资金流向", "涨跌停", "筹码分布", "概念/行业成分", "龙虎榜/游资", "板块热力"}
        ]

        return {
            "tushare_token_configured": bool(settings.tushare_token),
            "tushare_realtime_enabled": bool(settings.tushare_realtime_enabled),
            "tushare_history_enabled": bool(settings.tushare_history_enabled),
            "tushare_enrichment_enabled": bool(settings.tushare_enrichment_enabled),
            "tushare_http_url_configured": bool(settings.tushare_http_url),
            "tushare_http_url": settings.tushare_http_url,
            "last_tushare_error": (tushare_failures[0].get("failure_reason") if tushare_failures else None),
            "last_snapshot_source": snapshot_source,
            "last_history_source": history_source,
            "realtime_status": _diagnostic_status(realtime_status, fallback_source=snapshot_source, expected_source="Tushare 实时日线"),
            "history_status": _diagnostic_status(history_status, fallback_source=history_source, expected_source="Tushare daily 前复权"),
            "enrichment_status": _aggregate_diagnostic_status(enrichment_statuses),
            "rows": list(latest_by_source_cap.values()),
        }

    def runtime_health(
        self,
        now: Optional[datetime] = None,
        scheduler_enabled: bool = True,
        poll_seconds: int = 30,
        catchup_minutes: int = 8,
        schedule: str = "",
    ) -> Dict[str, Any]:
        current = now or datetime.now(CHINA_TZ)
        current = current.astimezone(CHINA_TZ) if current.tzinfo else current.replace(tzinfo=CHINA_TZ)
        today = current.date()
        task_rows = self.db.query(
            """
            SELECT id, status, stage, error_message, started_at, updated_at, finished_at, summary_json
            FROM task_runs
            WHERE kind = 'intraday'
              AND id LIKE ?
            ORDER BY started_at
            """,
            [f"intraday-auto-{today:%Y%m%d}-%"],
        )
        tasks_by_id = {row["id"]: row for row in task_rows}
        latest_task_slot = _latest_scheduled_task_slot(tasks_by_id)
        slots = []
        for hour, minute in parse_intraday_schedule(schedule):
            slot = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
            task_id = f"intraday-auto-{slot:%Y%m%d-%H%M}"
            task = tasks_by_id.get(task_id)
            status = _slot_status(current, slot, task, scheduler_enabled, catchup_minutes)
            if status == "due" and latest_task_slot and slot < latest_task_slot:
                status = "missed"
            sample_at = slot.replace(tzinfo=None)
            slots.append(
                {
                    "time": f"{hour:02d}:{minute:02d}",
                    "sample_at": sample_at,
                    "status": status,
                    "task_id": task_id if task else None,
                    "task_status": task.get("status") if task else None,
                    "stage": task.get("stage") if task else None,
                    "error_message": task.get("error_message") if task else None,
                    "sample_count": self.db.scalar(
                        "SELECT COUNT(*) FROM intraday_snapshots WHERE sample_at = ?",
                        [sample_at],
                    )
                    or 0,
                    "strict_count": self._intraday_rank_count(sample_at, "strict"),
                    "score_count": self._intraday_rank_count(sample_at, "score"),
                    "finished_at": task.get("finished_at") if task else None,
                }
            )
        queued = self.db.scalar("SELECT COUNT(*) FROM task_runs WHERE status = 'queued'") or 0
        running = self.db.scalar("SELECT COUNT(*) FROM task_runs WHERE status = 'running'") or 0
        next_slot = next((slot for slot in slots if slot["status"] in {"pending", "due"}), None)
        completed_slots = [
            slot
            for slot in slots
            if slot["status"] in {"completed_full", "completed_partial", "queued", "running"}
        ]
        latest_slot = completed_slots[-1] if completed_slots else None
        remaining_count = len([slot for slot in slots if slot["status"] in {"pending", "due"}])
        latest_sample = self.db.scalar("SELECT MAX(sample_at) FROM intraday_snapshots")
        return {
            "data": {
                "latest_history_date": self.db.scalar("SELECT MAX(date) FROM historical_bars"),
                "latest_snapshot_date": self.db.scalar("SELECT MAX(date) FROM daily_snapshots"),
                "latest_intraday_sample": latest_sample,
                "latest_brief_date": self.db.scalar("SELECT MAX(brief_date) FROM daily_briefs"),
                "stock_count": self.db.scalar("SELECT COUNT(*) FROM stock_basic") or 0,
            },
            "tasks": {
                "queued": queued,
                "running": running,
                "latest_update": self.latest_task("update"),
                "latest_analyze": self.latest_task("analyze"),
                "latest_intraday": self.latest_task("intraday"),
                "latest_brief": self.latest_task("brief"),
            },
            "scheduler": {
                "enabled": scheduler_enabled,
                "timezone": "Asia/Shanghai",
                "now": current.replace(tzinfo=None),
                "is_weekend": current.weekday() >= 5,
                "poll_seconds": poll_seconds,
                "catchup_minutes": catchup_minutes,
                "next_slot": next_slot,
                "slot_count": len(slots),
                "completed_count": len(completed_slots),
                "remaining_count": remaining_count,
                "latest_slot": latest_slot,
                "slots": slots,
            },
        }

    def list_stocks(
        self,
        limit: int = 50,
        offset: int = 0,
        search: str = "",
        exchange: str = "",
        board: str = "",
        status: str = "active",
    ) -> Dict[str, Any]:
        params: List[Any] = []
        clauses: List[str] = []
        exact_code_search = False
        if search:
            text = search.strip()
            exact_code_search = bool(re.fullmatch(r"\d{6}(\.(SH|SZ|BJ))?", text.upper()))
            clauses.append("(b.code ILIKE ? OR b.name ILIKE ?)")
            params.extend([f"%{text}%", f"%{text}%"])
        exchange = exchange.upper().strip()
        if exchange in {"SH", "SZ", "BJ"}:
            clauses.append("b.exchange = ?")
            params.append(exchange)
        board = board.lower().strip()
        if board in {"main", "gem", "star", "bj"}:
            clauses.append(f"{STOCK_BOARD_CASE} = ?")
            params.append(board)
        status = status.lower().strip()
        if status not in {"active", "inactive", "all"}:
            status = "active"
        if status == "inactive":
            clauses.append("b.suspended IS TRUE")
        elif status == "active" and not exact_code_search:
            clauses.append(ACTIVE_STOCK_FILTER)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        total = self.db.scalar(f"SELECT COUNT(*) FROM stock_basic b {where}", params) or 0
        rows = self.db.query(
            f"""
            SELECT b.code, b.name, b.exchange, b.list_date, b.source, b.is_st, b.suspended,
                   b.suspended IS DISTINCT FROM TRUE AS is_active,
                   CASE WHEN b.suspended IS TRUE THEN '非活跃' ELSE '活跃' END AS status_label,
                   {STOCK_BOARD_CASE} AS board,
                   s.latest_price, s.pct_chg, s.amount, s.volume,
                   COALESCE(dbs.turnover_rate, s.turnover_rate) AS turnover_rate,
                   f.float_market_value,
                   COALESCE(dbs.volume_ratio, hv.local_volume_ratio) AS volume_ratio,
                   CASE
                       WHEN dbs.volume_ratio IS NOT NULL THEN 'Tushare daily_basic'
                       WHEN hv.local_volume_ratio IS NOT NULL THEN '本地K线'
                       ELSE NULL
                   END AS volume_ratio_source,
                   mf.main_net_amount,
                   mf.net_mf_amount,
                   cyq.winner_rate,
                   cyq.cost_50pct,
                   (SELECT COUNT(*) FROM tushare_ths_member c WHERE c.code = b.code) AS concept_count,
                   (SELECT limit_type FROM tushare_limit_list_d l WHERE l.code = b.code ORDER BY trade_date DESC LIMIT 1) AS latest_limit_type,
                   (SELECT net_amount FROM tushare_top_list t WHERE t.code = b.code ORDER BY trade_date DESC LIMIT 1) AS latest_top_net_amount,
                   (SELECT COUNT(*) FROM historical_bars h WHERE h.code = b.code) AS history_days,
                   (SELECT MAX(date) FROM historical_bars h WHERE h.code = b.code) AS latest_history_date
            FROM stock_basic b
            LEFT JOIN daily_snapshots s
              ON s.code = b.code
             AND s.date = (SELECT MAX(date) FROM daily_snapshots)
            LEFT JOIN float_market_values f
              ON f.code = b.code
             AND f.date = (SELECT MAX(date) FROM float_market_values)
            LEFT JOIN tushare_daily_basic dbs
              ON dbs.code = b.code
             AND dbs.trade_date = (SELECT MAX(trade_date) FROM tushare_daily_basic WHERE code = b.code)
            {LOCAL_VOLUME_RATIO_JOIN}
            LEFT JOIN tushare_moneyflow mf
              ON mf.code = b.code
             AND mf.trade_date = (SELECT MAX(trade_date) FROM tushare_moneyflow WHERE code = b.code)
            LEFT JOIN tushare_cyq_perf cyq
              ON cyq.code = b.code
             AND cyq.trade_date = (SELECT MAX(trade_date) FROM tushare_cyq_perf WHERE code = b.code)
            {where}
            ORDER BY b.code
            LIMIT ? OFFSET ?
            """,
            params + [max(1, min(limit, 500)), max(0, offset)],
        )
        return {"rows": rows, "total": total, "limit": limit, "offset": offset}

    def stock_detail(self, code: str) -> Dict[str, Any]:
        target = code.strip().upper()
        basic_rows = self.db.query(
            f"""
            SELECT b.code, b.name, b.exchange, b.list_date, b.source, b.is_st, b.suspended,
                   {STOCK_BOARD_CASE} AS board,
                   s.latest_price, s.pct_chg, s.amount, s.volume,
                   COALESCE(dbs.turnover_rate, s.turnover_rate) AS turnover_rate,
                   COALESCE(dbs.volume_ratio, hv.local_volume_ratio) AS volume_ratio,
                   CASE
                       WHEN dbs.volume_ratio IS NOT NULL THEN 'Tushare daily_basic'
                       WHEN hv.local_volume_ratio IS NOT NULL THEN '本地K线'
                       ELSE NULL
                   END AS volume_ratio_source,
                   f.float_market_value,
                   (SELECT COUNT(*) FROM historical_bars h WHERE h.code = b.code) AS history_days,
                   (SELECT MAX(date) FROM historical_bars h WHERE h.code = b.code) AS latest_history_date
            FROM stock_basic b
            LEFT JOIN daily_snapshots s
              ON s.code = b.code
             AND s.date = (SELECT MAX(date) FROM daily_snapshots WHERE code = b.code)
            LEFT JOIN float_market_values f
              ON f.code = b.code
             AND f.date = (SELECT MAX(date) FROM float_market_values WHERE code = b.code)
            LEFT JOIN tushare_daily_basic dbs
              ON dbs.code = b.code
             AND dbs.trade_date = (SELECT MAX(trade_date) FROM tushare_daily_basic WHERE code = b.code)
            {LOCAL_VOLUME_RATIO_JOIN}
            WHERE b.code = ?
            LIMIT 1
            """,
            [target],
        )
        if not basic_rows:
            return {"basic": None}
        basic = basic_rows[0]
        daily_basic = self._latest_code_row("tushare_daily_basic", target)
        if basic.get("volume_ratio") is not None and (not daily_basic or daily_basic.get("volume_ratio") is None):
            daily_basic = dict(daily_basic or {})
            daily_basic.setdefault("code", target)
            daily_basic.setdefault("trade_date", basic.get("latest_history_date"))
            daily_basic.setdefault("source", "本地K线")
            daily_basic["volume_ratio"] = basic.get("volume_ratio")
            daily_basic["volume_ratio_source"] = basic.get("volume_ratio_source") or "本地K线"
        elif daily_basic and daily_basic.get("volume_ratio") is not None:
            daily_basic = dict(daily_basic)
            daily_basic["volume_ratio_source"] = "Tushare daily_basic"
        return {
            "basic": basic,
            "daily_basic": daily_basic,
            "factor": self._latest_code_row("tushare_stk_factor", target),
            "moneyflow": self._latest_code_row("tushare_moneyflow", target),
            "cyq_perf": self._latest_code_row("tushare_cyq_perf", target),
            "concepts": self.db.query(
                """
                SELECT con_code, con_name, weight, in_date, out_date, is_new, updated_at
                FROM tushare_ths_member
                WHERE code = ?
                ORDER BY updated_at DESC, con_name
                LIMIT 20
                """,
                [target],
            ),
            "limit_events": self.db.query(
                """
                SELECT trade_date, limit_type, open_times, fd_amount, up_stat
                FROM tushare_limit_list_d
                WHERE code = ?
                ORDER BY trade_date DESC
                LIMIT 10
                """,
                [target],
            ),
            "top_events": self.db.query(
                """
                SELECT trade_date, reason, net_amount, amount_rate
                FROM tushare_top_list
                WHERE code = ?
                ORDER BY trade_date DESC
                LIMIT 10
                """,
                [target],
            ),
            "history": self.db.query(
                """
                SELECT date, close, pct_chg, amount, turn
                FROM historical_bars
                WHERE code = ?
                ORDER BY date DESC
                LIMIT 30
                """,
                [target],
            ),
        }

    def _latest_code_row(self, table: str, code: str) -> Optional[Dict[str, Any]]:
        rows = self.db.query(
            f"""
            SELECT *
            FROM {table}
            WHERE code = ?
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            [code],
        )
        return rows[0] if rows else None

    def latest_task(self, kind: str) -> Optional[Dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM task_runs WHERE kind = ? ORDER BY started_at DESC LIMIT 1",
            [kind],
        )
        if not rows:
            return None
        row = rows[0]
        row["summary"] = json.loads(row.pop("summary_json") or "{}")
        row.pop("payload_json", None)
        row.pop("queue_order", None)
        return row

    def task_runs(self, statuses: Optional[List[str]] = None, limit: int = 50) -> List[Dict[str, Any]]:
        clean_statuses = [str(status).strip() for status in statuses or [] if str(status).strip()]
        params: List[Any] = []
        where = ""
        if clean_statuses:
            where = f"WHERE status IN ({', '.join(['?'] * len(clean_statuses))})"
            params.extend(clean_statuses)
        params.append(max(1, min(int(limit or 50), 200)))
        rows = self.db.query(
            f"""
            SELECT *
            FROM task_runs
            {where}
            ORDER BY queue_order NULLS LAST, started_at DESC, updated_at DESC, id
            LIMIT ?
            """,
            params,
        )
        for row in rows:
            row["summary"] = json.loads(row.pop("summary_json") or "{}")
            row.pop("payload_json", None)
            row.pop("queue_order", None)
        return rows

    def latest_daily_brief(self) -> Optional[Dict[str, Any]]:
        rows = self.db.query("SELECT * FROM daily_briefs ORDER BY generated_at DESC LIMIT 1")
        if not rows:
            return None
        row = rows[0]
        payload = json.loads(row.get("payload_json") or "{}")
        article_flow = self._latest_daily_brief_article_flow(row, payload.get("article_flow"))
        return {
            "id": row["id"],
            "brief_date": row.get("brief_date"),
            "status": row.get("status"),
            "hero_headline": row.get("hero_headline") or "",
            "daily_overview": row.get("daily_overview") or "",
            "tech_briefs": json.loads(row.get("tech_briefs_json") or "[]"),
            "finance_briefs": json.loads(row.get("finance_briefs_json") or "[]"),
            "politics_briefs": json.loads(row.get("politics_briefs_json") or "[]"),
            "editor_note": row.get("editor_note") or "",
            "keywords": json.loads(row.get("keywords_json") or "[]"),
            "article_count": row.get("article_count") or 0,
            "source_count": row.get("source_count") or 0,
            "llm_model": row.get("llm_model"),
            "generated_at": row.get("generated_at"),
            "error_message": row.get("error_message"),
            "article_flow": article_flow,
        }

    def _latest_daily_brief_article_flow(
        self,
        row: Dict[str, Any],
        existing_flow: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        brief_date = row.get("brief_date")
        flow: Dict[str, List[Dict[str, Any]]] = {"tech": [], "finance": [], "politics": []}
        if isinstance(existing_flow, dict):
            for category in flow:
                values = existing_flow.get(category) or []
                flow[category] = [item for item in values if isinstance(item, dict) and not _is_blocked_brief_source(item)] if isinstance(values, list) else []
        has_llm_flow = bool(row.get("llm_model") and row.get("llm_model") != "fallback" and any(flow.values()))
        for category in flow:
            seen = {str(item.get("url") or item.get("title") or "") for item in flow[category] if isinstance(item, dict)}
            rows = self.db.query(
                """
                SELECT title, url, source, category, excerpt, published_at
                FROM news_articles
                WHERE category = ?
                  AND (
                    ? IS NULL
                    OR CAST(COALESCE(published_at, fetched_at) AS DATE) <= CAST(? AS DATE)
                  )
                ORDER BY COALESCE(published_at, fetched_at) DESC NULLS LAST
                LIMIT 80
                """,
                [category, brief_date, brief_date],
            )
            by_url = {str(item.get("url") or ""): item for item in rows if item.get("url")}
            enriched = []
            for item in flow[category]:
                if _is_blocked_brief_source(item):
                    continue
                row_item = dict(item)
                metadata = by_url.get(str(row_item.get("url") or ""))
                if metadata:
                    row_item["published_at"] = row_item.get("published_at") or _format_brief_published(metadata.get("published_at"))
                    row_item["source"] = row_item.get("source") or metadata.get("source") or ""
                    row_item["category"] = row_item.get("category") or metadata.get("category") or category
                enriched.append(row_item)
            flow[category] = sorted(enriched, key=_brief_article_sort_key, reverse=True)
            if has_llm_flow:
                continue
            for item in rows:
                if _is_blocked_brief_source(item):
                    continue
                key = str(item.get("url") or item.get("title") or "")
                if key in seen:
                    continue
                seen.add(key)
                flow[category].append(
                    {
                        "title": item.get("title") or "",
                        "url": item.get("url") or "",
                        "source": item.get("source") or "",
                        "category": item.get("category") or category,
                        "summary": (item.get("excerpt") or "")[:260],
                        "published_at": _format_brief_published(item.get("published_at")),
                    }
                )
                if len(flow[category]) >= 80:
                    break
            flow[category] = sorted(flow[category], key=_brief_article_sort_key, reverse=True)[:80]
        return flow

    def _intraday_rank_count(self, sample_at: datetime, mode: str) -> int:
        return int(
            self.db.scalar(
                """
                SELECT COUNT(*)
                FROM intraday_radar_rankings
                WHERE sample_at = ?
                  AND radar_mode = ?
                """,
                [sample_at, mode],
            )
            or 0
        )

    def latest_analysis_run(self) -> Optional[Dict[str, Any]]:
        rows = self.db.query("SELECT * FROM analysis_runs ORDER BY started_at DESC LIMIT 1")
        if not rows:
            return None
        row = self._decode_analysis_row(rows[0])
        row["funnel"] = self.db.query(
            "SELECT * FROM funnel_stats WHERE run_id = ? ORDER BY order_index",
            [row["id"]],
        )
        return row

    def analysis_runs(self) -> List[Dict[str, Any]]:
        rows = self.db.query("SELECT * FROM analysis_runs ORDER BY started_at DESC LIMIT 20")
        for row in rows:
            decoded = self._decode_analysis_row(row)
            row.clear()
            row.update(decoded)
        return rows

    def latest_backtest_run(self) -> Optional[Dict[str, Any]]:
        rows = self.db.query("SELECT * FROM backtest_runs ORDER BY started_at DESC LIMIT 1")
        if not rows:
            return None
        return self._decode_backtest_row(rows[0])

    def backtest_runs(self) -> List[Dict[str, Any]]:
        rows = self.db.query("SELECT * FROM backtest_runs ORDER BY started_at DESC LIMIT 20")
        return [self._decode_backtest_row(row) for row in rows]

    def backtest_result(self, run_id: Optional[str] = None, limit: int = 500) -> Dict[str, Any]:
        target = run_id or self.db.scalar(
            "SELECT id FROM backtest_runs ORDER BY started_at DESC LIMIT 1"
        )
        if not target:
            return {"run": None, "signals": []}
        runs = self.db.query("SELECT * FROM backtest_runs WHERE id = ?", [target])
        if not runs:
            return {"run": None, "signals": []}
        rows = self.db.query(
            """
            SELECT *
            FROM backtest_signals
            WHERE run_id = ?
            ORDER BY as_of_date DESC, rank
            LIMIT ?
            """,
            [target, max(1, min(limit, 2000))],
        )
        for row in rows:
            row["reasons"] = json.loads(row.pop("reasons_json") or "[]")
            row["metrics"] = json.loads(row.pop("metrics_json") or "{}")
        return {"run": self._decode_backtest_row(runs[0]), "signals": rows}

    def analysis_reports(self, per_mode_limit: int = 3) -> Dict[str, Any]:
        rows = self.db.query(
            """
            SELECT *
            FROM analysis_runs
            WHERE status LIKE 'completed%'
            ORDER BY finished_at DESC NULLS LAST, started_at DESC
            LIMIT 300
            """
        )
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            decoded = self._decode_analysis_row(row)
            signal_mode = decoded.get("config", {}).get("signal_mode") or "unknown"
            reports = groups.setdefault(signal_mode, [])
            if len(reports) < max(1, min(per_mode_limit, 10)):
                reports.append(decoded)
        return {
            "groups": [
                {"signal_mode": signal_mode, "reports": reports}
                for signal_mode, reports in groups.items()
            ]
        }

    def analysis_report(self, run_id: str, limit: int = 100) -> Dict[str, Any]:
        rows = self.db.query("SELECT * FROM analysis_runs WHERE id = ?", [run_id])
        if not rows:
            return {"analysis": None, "candidates": {"run_id": None, "rows": [], "funnel": [], "zero_reason": "分析报告不存在。"}}
        analysis = self._decode_analysis_row(rows[0])
        analysis["funnel"] = self.db.query(
            "SELECT * FROM funnel_stats WHERE run_id = ? ORDER BY order_index",
            [run_id],
        )
        return {"analysis": analysis, "candidates": self.candidates(run_id=run_id, limit=limit)}

    def candidates(self, run_id: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        target = run_id or self.db.scalar(
            "SELECT id FROM analysis_runs WHERE status LIKE 'completed%' ORDER BY started_at DESC LIMIT 1"
        )
        if not target:
            return {"run_id": None, "rows": [], "funnel": [], "zero_reason": "尚未运行分析。"}
        rows = self.db.query(
            """
            SELECT *
            FROM candidate_results
            WHERE run_id = ?
            ORDER BY rank
            LIMIT ?
            """,
            [target, max(1, min(limit, 500))],
        )
        for row in rows:
            row["data_sources"] = json.loads(row.get("data_sources") or "{}")
            row["reasons"] = json.loads(row.pop("reasons_json") or "[]")
            row["metrics"] = json.loads(row.pop("metrics_json") or "{}")
        run = self.db.query("SELECT summary_json FROM analysis_runs WHERE id = ?", [target])
        summary = json.loads(run[0]["summary_json"] or "{}") if run else {}
        return {
            "run_id": target,
            "rows": rows,
            "funnel": self.db.query(
                "SELECT * FROM funnel_stats WHERE run_id = ? ORDER BY order_index",
                [target],
            ),
            "zero_reason": summary.get("zero_reason"),
        }

    @staticmethod
    def _decode_analysis_row(row: Dict[str, Any]) -> Dict[str, Any]:
        decoded = dict(row)
        decoded["summary"] = json.loads(decoded.pop("summary_json") or "{}")
        decoded["config"] = json.loads(decoded.pop("config_json") or "{}")
        return decoded

    @staticmethod
    def _decode_backtest_row(row: Dict[str, Any]) -> Dict[str, Any]:
        decoded = dict(row)
        decoded["summary"] = json.loads(decoded.pop("summary_json") or "{}")
        decoded["config"] = json.loads(decoded.pop("config_json") or "{}")
        return decoded

    def capabilities(self) -> List[Dict[str, Any]]:
        self.refresh_capabilities()
        rows = self.db.query("SELECT * FROM data_capabilities ORDER BY capability")
        if {row["capability"] for row in rows} != set(CAPABILITY_DEFINITIONS):
            rows = self.db.query("SELECT * FROM data_capabilities ORDER BY capability")
        for row in rows:
            row["actual_sources"] = json.loads(row.get("actual_sources") or "[]")
            row["fallback_sources"] = json.loads(row.get("fallback_sources") or "[]")
        return rows

    def refresh_capabilities(self) -> None:
        total_stocks = self.db.scalar("SELECT COUNT(*) FROM stock_basic") or 0
        active_stocks = self.active_stock_count()
        latest_history = self.db.scalar("SELECT MAX(date) FROM historical_bars")
        latest_snapshot = self.db.scalar(
            f"""
            SELECT MAX(s.date)
            FROM daily_snapshots s
            JOIN stock_basic b ON b.code = s.code
            WHERE {ACTIVE_STOCK_FILTER}
            """
        )
        latest_market_environment = self.db.scalar("SELECT MAX(date) FROM market_environment")
        latest_tushare_daily_basic = self.db.scalar(
            f"""
            SELECT MAX(t.trade_date)
            FROM tushare_daily_basic t
            JOIN stock_basic b ON b.code = t.code
            WHERE {ACTIVE_STOCK_FILTER}
            """
        )
        latest_tushare_stk_factor = self.db.scalar(
            f"""
            SELECT MAX(t.trade_date)
            FROM tushare_stk_factor t
            JOIN stock_basic b ON b.code = t.code
            WHERE {ACTIVE_STOCK_FILTER}
            """
        )
        latest_tushare_moneyflow = self.db.scalar(
            f"""
            SELECT MAX(t.trade_date)
            FROM tushare_moneyflow t
            JOIN stock_basic b ON b.code = t.code
            WHERE {ACTIVE_STOCK_FILTER}
            """
        )
        latest_tushare_limit = self.db.scalar("SELECT MAX(trade_date) FROM tushare_limit_list_d")
        latest_tushare_cyq = self.db.scalar(
            f"""
            SELECT MAX(trade_date)
            FROM (
                SELECT p.trade_date
                FROM tushare_cyq_perf p
                JOIN stock_basic b ON b.code = p.code
                WHERE {ACTIVE_STOCK_FILTER}
                UNION ALL
                SELECT c.trade_date
                FROM tushare_cyq_chips c
                JOIN stock_basic b ON b.code = c.code
                WHERE {ACTIVE_STOCK_FILTER}
            )
            """
        )
        latest_tushare_ths = self.db.scalar(
            f"""
            SELECT MAX(t.updated_at)
            FROM tushare_ths_member t
            JOIN stock_basic b ON b.code = t.code
            WHERE {ACTIVE_STOCK_FILTER}
            """
        )
        latest_tushare_top = self.db.scalar(
            """
            SELECT MAX(trade_date)
            FROM (
                SELECT trade_date FROM tushare_top_list
                UNION ALL
                SELECT trade_date FROM tushare_top_inst
                UNION ALL
                SELECT trade_date FROM tushare_hm_detail
            )
            """
        )
        latest_sector_heat = self.db.scalar("SELECT MAX(trade_date) FROM market_sector_daily")
        latest_float_market_value = self.db.scalar(
            f"""
            SELECT MAX(date)
            FROM (
                SELECT f.date
                FROM float_market_values f
                JOIN stock_basic b ON b.code = f.code
                WHERE f.float_market_value IS NOT NULL
                  AND {ACTIVE_STOCK_FILTER}
                UNION ALL
                SELECT s.date
                FROM daily_snapshots s
                JOIN stock_basic b ON b.code = s.code
                WHERE s.float_market_value IS NOT NULL
                  AND {ACTIVE_STOCK_FILTER}
            )
            """
        )
        float_market_value_count = 0
        if latest_float_market_value:
            float_market_value_count = (
                self.db.scalar(
                    """
                    SELECT COUNT(DISTINCT code)
                    FROM (
                        SELECT f.code
                        FROM float_market_values f
                        JOIN stock_basic b ON b.code = f.code
                        WHERE f.date = ? AND f.float_market_value IS NOT NULL
                          AND b.suspended IS DISTINCT FROM TRUE
                        UNION
                        SELECT s.code
                        FROM daily_snapshots s
                        JOIN stock_basic b ON b.code = s.code
                        WHERE s.date = ? AND s.float_market_value IS NOT NULL
                          AND b.suspended IS DISTINCT FROM TRUE
                    )
                    """,
                    [latest_float_market_value, latest_float_market_value],
                )
                or 0
            )
        status_failures = self.db.query(
            """
            SELECT capability, failure_reason, COALESCE(last_failure, last_checked) AS failure_at
            FROM source_status
            WHERE failure_reason IS NOT NULL
            QUALIFY ROW_NUMBER() OVER (PARTITION BY capability ORDER BY last_checked DESC) = 1
            """
        )
        failure_by_cap = {row["capability"]: row for row in status_failures}

        def latest_code_count(table: str, latest: Any) -> int:
            if not latest:
                return 0
            return int(
                self.db.scalar(
                    f"""
                    SELECT COUNT(DISTINCT t.code)
                    FROM {table} t
                    JOIN stock_basic b ON b.code = t.code
                    WHERE t.trade_date = ?
                      AND {ACTIVE_STOCK_FILTER}
                    """,
                    [latest],
                )
                or 0
            )

        latest_cyq_count = 0
        if latest_tushare_cyq:
            latest_cyq_count = int(
                self.db.scalar(
                    """
                    SELECT COUNT(DISTINCT code)
                    FROM (
                        SELECT p.code
                        FROM tushare_cyq_perf p
                        JOIN stock_basic b ON b.code = p.code
                        WHERE p.trade_date = ?
                          AND b.suspended IS DISTINCT FROM TRUE
                        UNION
                        SELECT c.code
                        FROM tushare_cyq_chips c
                        JOIN stock_basic b ON b.code = c.code
                        WHERE c.trade_date = ?
                          AND b.suspended IS DISTINCT FROM TRUE
                    )
                    """,
                    [latest_tushare_cyq, latest_tushare_cyq],
                )
                or 0
            )
        latest_top_count = 0
        if latest_tushare_top:
            latest_top_count = int(
                self.db.scalar(
                    """
                    SELECT COUNT(DISTINCT code)
                    FROM (
                        SELECT code FROM tushare_top_list WHERE trade_date = ?
                        UNION
                        SELECT code FROM tushare_top_inst WHERE trade_date = ?
                        UNION
                        SELECT code FROM tushare_hm_detail WHERE trade_date = ?
                    )
                    """,
                    [latest_tushare_top, latest_tushare_top, latest_tushare_top],
                )
                or 0
            )

        rows = []
        counts = {
            "历史 K 线": self.db.scalar(
                f"""
                SELECT COUNT(DISTINCT h.code)
                FROM historical_bars h
                JOIN stock_basic b ON b.code = h.code
                WHERE {ACTIVE_STOCK_FILTER}
                """
            )
            or 0,
            "当天行情快照": self.db.scalar(
                f"""
                SELECT COUNT(DISTINCT s.code)
                FROM daily_snapshots s
                JOIN stock_basic b ON b.code = s.code
                WHERE s.date = ?
                  AND {ACTIVE_STOCK_FILTER}
                """,
                [latest_snapshot],
            )
            or 0,
            "股票基础信息": active_stocks,
            "流通市值": float_market_value_count,
            "换手率": self.db.scalar(
                f"""
                SELECT COUNT(DISTINCT h.code)
                FROM historical_bars h
                JOIN stock_basic b ON b.code = h.code
                WHERE h.turn IS NOT NULL
                  AND {ACTIVE_STOCK_FILTER}
                """
            )
            or 0,
            "RPS": self.db.scalar(
                f"""
                SELECT COUNT(*)
                FROM (
                    SELECT h.code, COUNT(*) AS n
                    FROM historical_bars h
                    JOIN stock_basic b ON b.code = h.code
                    WHERE {ACTIVE_STOCK_FILTER}
                    GROUP BY h.code
                    HAVING n >= 21
                )
                """
            )
            or 0,
            "振幅": self.db.scalar(
                f"""
                SELECT COUNT(DISTINCT h.code)
                FROM historical_bars h
                JOIN stock_basic b ON b.code = h.code
                WHERE h.high IS NOT NULL
                  AND h.low IS NOT NULL
                  AND h.prev_close IS NOT NULL
                  AND {ACTIVE_STOCK_FILTER}
                """
            )
            or 0,
            "ST / 停牌状态": self.db.scalar(
                f"""
                SELECT COUNT(DISTINCT h.code)
                FROM historical_bars h
                JOIN stock_basic b ON b.code = h.code
                WHERE (h.is_st IS NOT NULL OR h.tradestatus IS NOT NULL)
                  AND {ACTIVE_STOCK_FILTER}
                """
            )
            or 0,
            "市场环境": self.db.scalar("SELECT COUNT(*) FROM market_environment") or 0,
            "每日指标": latest_code_count("tushare_daily_basic", latest_tushare_daily_basic),
            "技术因子": latest_code_count("tushare_stk_factor", latest_tushare_stk_factor),
            "资金流向": latest_code_count("tushare_moneyflow", latest_tushare_moneyflow),
            "涨跌停": latest_code_count("tushare_limit_list_d", latest_tushare_limit),
            "筹码分布": latest_cyq_count,
            "概念/行业成分": self.db.scalar(
                f"""
                SELECT COUNT(DISTINCT t.code)
                FROM tushare_ths_member t
                JOIN stock_basic b ON b.code = t.code
                WHERE {ACTIVE_STOCK_FILTER}
                """
            )
            or 0,
            "龙虎榜/游资": latest_top_count,
            "板块热力": self.db.scalar("SELECT COUNT(*) FROM market_sector_daily WHERE trade_date = ?", [latest_sector_heat]) or 0,
        }
        source_rows = self.db.query(
            """
            SELECT capability, source, COALESCE(last_success, last_checked) AS success_at
            FROM source_status
            WHERE status IN ('available', 'completed_full', 'completed_partial')
            """
        )
        success_candidates_by_cap: Dict[str, List[Dict[str, Any]]] = {}
        latest_success_by_cap: Dict[str, datetime] = {}
        for row in source_rows:
            capability = row["capability"]
            success_at = _coerce_datetime(row.get("success_at"))
            latest_success = latest_success_by_cap.get(capability)
            if latest_success is None or (success_at and success_at > latest_success):
                if success_at:
                    latest_success_by_cap[capability] = success_at
            success_candidates_by_cap.setdefault(capability, []).append(row)
        sources_by_cap: Dict[str, List[str]] = {}
        for capability, rows_for_capability in success_candidates_by_cap.items():
            latest_success = latest_success_by_cap.get(capability)
            sources: List[str] = []
            for row in rows_for_capability:
                source = row["source"]
                success_at = _coerce_datetime(row.get("success_at"))
                if latest_success and success_at and latest_success - success_at <= timedelta(minutes=30) and source not in sources:
                    sources.append(source)
            sources_by_cap[capability] = sources

        for capability, definition in CAPABILITY_DEFINITIONS.items():
            coverage = int(counts.get(capability, 0))
            coverage_kind = definition.get("coverage_kind", "stock")
            denominator = coverage if coverage_kind in {"event", "dataset"} else active_stocks if active_stocks else coverage
            missing_count = max(0, int(denominator) - coverage)
            failure = failure_by_cap.get(capability)
            failure_at = _coerce_datetime((failure or {}).get("failure_at"))
            latest_success = latest_success_by_cap.get(capability)
            failure_is_current = bool(failure) and (latest_success is None or failure_at is None or failure_at > latest_success)
            last_failure_reason = failure.get("failure_reason") if failure_is_current and (coverage <= 0 or missing_count > 0) else None
            latest_update = latest_snapshot if capability == "当天行情快照" else latest_history
            if capability == "流通市值":
                latest_update = latest_float_market_value
            elif capability == "市场环境":
                latest_update = latest_market_environment
            elif capability == "每日指标":
                latest_update = latest_tushare_daily_basic
            elif capability == "技术因子":
                latest_update = latest_tushare_stk_factor
            elif capability == "资金流向":
                latest_update = latest_tushare_moneyflow
            elif capability == "涨跌停":
                latest_update = latest_tushare_limit
            elif capability == "筹码分布":
                latest_update = latest_tushare_cyq
            elif capability == "概念/行业成分":
                latest_update = latest_tushare_ths
            elif capability == "龙虎榜/游资":
                latest_update = latest_tushare_top
            elif capability == "板块热力":
                latest_update = latest_sector_heat
            rows.append(
                {
                    "capability": capability,
                    "actual_sources": sources_by_cap.get(capability, []),
                    "fallback_sources": definition["fallback_sources"],
                    "coverage_count": coverage,
                    "missing_count": missing_count,
                    "latest_update": latest_update,
                    "last_failure_reason": last_failure_reason,
                    "uses_cache": True,
                    "can_backfill": definition["can_backfill"],
                    "participates_in_analysis": definition["participates_in_analysis"],
                    "updated_at": datetime.utcnow(),
                }
            )
        placeholders = ", ".join(["?"] * len(CAPABILITY_DEFINITIONS))
        self.db.execute(
            f"DELETE FROM data_capabilities WHERE capability NOT IN ({placeholders})",
            list(CAPABILITY_DEFINITIONS.keys()),
            write=True,
        )
        self.db.upsert("data_capabilities", rows, ["capability"])

    def _latest_market_environment(self) -> Optional[Dict[str, Any]]:
        rows = self.db.query("SELECT * FROM market_environment ORDER BY date DESC LIMIT 1")
        if not rows:
            return None
        row = rows[0]
        row["summary"] = json.loads(row.pop("summary_json") or "{}")
        return row

    def _market_state(self, environment: Optional[Dict[str, Any]], sector_nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not environment:
            score = 0.0
        else:
            sector_score = _avg_value(sector_nodes[:10], "heat_score")
            score = (
                (safe_float(environment.get("breadth_score")) or 50) * 0.25
                + (safe_float(environment.get("index_score")) or 50) * 0.20
                + (safe_float(environment.get("turnover_score")) or 50) * 0.15
                + (safe_float(environment.get("limit_score")) or 50) * 0.15
                + (sector_score if sector_score is not None else 50) * 0.15
                + _risk_adjustment(environment) * 0.10
            )
        label = _market_label(score)
        risk_level = "低" if score >= 70 else "中" if score >= 50 else "高" if score >= 35 else "极高"
        suggested_position = _suggested_position(score)
        top_sector = sector_nodes[0]["name"] if sector_nodes else None
        return {
            "trade_date": environment.get("date") if environment else None,
            "label": label,
            "score": round(score, 2),
            "suggested_position": suggested_position,
            "risk_level": risk_level,
            "headline": f"市场{label}，建议仓位 {suggested_position}" + (f"，主线关注 {top_sector}" if top_sector else ""),
            "key_risks": _market_risks(environment, score),
            "key_opportunities": ([f"{top_sector} 资金和热度靠前"] if top_sector else ["等待板块热力数据补齐"]),
        }

    def _daily_action_items(self, state: Dict[str, Any], sector_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items = []
        if state["risk_level"] in {"高", "极高"}:
            items.append(
                {
                    "id": "market-risk",
                    "priority": "high",
                    "category": "risk",
                    "title": "市场风险升高",
                    "description": "先处理高位、放量滞涨和观察池弱势样本。",
                    "target_type": "system",
                    "action": "review",
                }
            )
        if sector_nodes:
            leader = sector_nodes[0]
            items.append(
                {
                    "id": f"sector-{leader['code']}",
                    "priority": "medium",
                    "category": "opportunity",
                    "title": f"主线候选：{leader['name']}",
                    "description": f"热度 {leader.get('heat_score') or 0:.1f}，领涨股 {leader.get('leader_name') or '待确认'}。",
                    "target_type": "sector",
                    "target_code": leader["code"],
                    "action": "review",
                }
            )
        stale = [item for item in self._data_freshness() if item["status"] != "fresh"]
        if stale:
            items.append(
                {
                    "id": "data-stale",
                    "priority": "medium",
                    "category": "data",
                    "title": "存在数据待同步",
                    "description": "打开任务状态页检查同步 DAG 和失败原因。",
                    "target_type": "system",
                    "action": "sync_data",
                }
            )
        return items or [
            {
                "id": "run-strategy",
                "priority": "low",
                "category": "strategy",
                "title": "运行策略刷新候选",
                "description": "市场状态已更新，可以运行 Scanner 查看今日候选。",
                "target_type": "strategy",
                "action": "run_strategy",
            }
        ]

    def _data_freshness(self) -> List[Dict[str, Any]]:
        rows = [
            ("历史行情", self.db.scalar("SELECT MAX(date) FROM historical_bars")),
            ("今日行情", self.db.scalar("SELECT MAX(date) FROM daily_snapshots")),
            ("补充交易数据", self.db.scalar("SELECT MAX(trade_date) FROM tushare_daily_basic")),
            ("市场环境", self.db.scalar("SELECT MAX(date) FROM market_environment")),
            ("板块热力", self.db.scalar("SELECT MAX(trade_date) FROM market_sector_daily")),
        ]
        latest = max([_date_value(value) for _, value in rows if _date_value(value)] or [None])
        output = []
        for label, value in rows:
            item_date = _date_value(value)
            output.append(
                {
                    "label": label,
                    "latest_update": value,
                    "latest_date": value,
                    "status": "normal" if item_date and latest and item_date >= latest else "stale" if item_date else "missing",
                    "message": "已同步至最近交易日" if item_date and latest and item_date >= latest else "需要同步今日数据" if item_date else "暂未同步",
                }
            )
        return output

    @staticmethod
    def _ratio(count: int, total: int) -> Dict[str, Any]:
        return {
            "count": count,
            "total": total,
            "percent": round((count / total * 100) if total else 0, 2),
        }


def _date_value(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _round(value: Any) -> Optional[float]:
    number = safe_float(value)
    return round(number, 2) if number is not None else None


def _avg_value(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = [safe_float(row.get(key)) for row in rows]
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 2)


def _risk_adjustment(environment: Dict[str, Any]) -> float:
    if not environment:
        return 50
    score = 50.0
    limit_down = safe_float(environment.get("limit_down_count")) or 0
    weak = safe_float(environment.get("weak_count")) or 0
    up = safe_float(environment.get("up_count")) or 0
    down = safe_float(environment.get("down_count")) or 0
    score -= limit_down * 2.5
    score -= weak * 0.15
    if down > up:
        score -= min(20, (down - up) / max(up + down, 1) * 40)
    return max(0, min(100, score))


def _market_label(score: float) -> str:
    if score >= 80:
        return "强势"
    if score >= 65:
        return "回暖"
    if score >= 50:
        return "震荡"
    if score >= 35:
        return "偏弱"
    if score >= 20:
        return "退潮"
    return "极端风险"


def _suggested_position(score: float) -> str:
    if score >= 80:
        return "80%-100%"
    if score >= 65:
        return "60%-80%"
    if score >= 50:
        return "40%-60%"
    if score >= 35:
        return "20%-40%"
    return "0%-20%"


def _market_risks(environment: Optional[Dict[str, Any]], score: float) -> List[str]:
    risks = []
    if not environment:
        return ["市场环境数据缺失"]
    if score < 50:
        risks.append("市场分数低于中性区间")
    if (safe_float(environment.get("limit_down_count")) or 0) > 0:
        risks.append("跌停数量需要关注")
    if (safe_float(environment.get("weak_count")) or 0) > (safe_float(environment.get("strong_count")) or 0):
        risks.append("弱势股数量高于强势股")
    return risks or ["暂未发现显著系统性风险"]
