from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.config import settings
from backend.app.db import Database


ACTIVE_STOCK_FILTER = "b.suspended IS DISTINCT FROM TRUE"


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


    def review_overview(self) -> Dict[str, Any]:
        rows = self.db.query("""
            WITH latest AS (SELECT MAX(date) AS trade_date FROM historical_bars)
            SELECT latest.trade_date,
                (SELECT COUNT(*) FROM stock_basic WHERE suspended IS DISTINCT FROM TRUE) AS stock_count,
                (SELECT COUNT(*) FROM historical_bars) AS history_rows,
                (SELECT COUNT(*) FROM historical_bars h JOIN stock_basic b USING (code)
                 WHERE h.date = latest.trade_date AND b.suspended IS DISTINCT FROM TRUE) AS covered_count
            FROM latest
        """)
        return {
            **rows[0],
            "latest_update": self.latest_task("update"),
            "latest_analysis": self.latest_analysis_run(),
            "source": "Baostock 日线（前复权）",
            "schedule_enabled": settings.daily_update_scheduler_enabled,
            "schedule_time": settings.daily_update_schedule_time,
        }


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
        dag_order = {"stock_basic": 0, "history_qfq": 1}
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


    def source_diagnostics(self) -> Dict[str, Any]:
        rows = self.db.query("SELECT * FROM source_status WHERE source IN ('Baostock', '本地历史 K 线', '本地缓存') ORDER BY last_checked DESC")
        for row in rows:
            row["payload"] = json.loads(row.pop("payload_json") or "{}")
        return {"rows": rows}


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
        terminal_statuses = {"completed_full", "completed_partial", "failed", "skipped"}
        active_statuses = {"queued", "running"}
        params: List[Any] = []
        where = ""
        if clean_statuses:
            where = f"WHERE status IN ({', '.join(['?'] * len(clean_statuses))})"
            params.extend(clean_statuses)
        if clean_statuses and set(clean_statuses).issubset(terminal_statuses):
            order_by = "COALESCE(finished_at, updated_at, started_at) DESC, updated_at DESC, started_at DESC, id DESC"
        elif clean_statuses and set(clean_statuses).issubset(active_statuses):
            order_by = "(queue_order IS NULL), queue_order, started_at, id"
        else:
            order_by = """
                CASE WHEN status IN ('queued', 'running') THEN 0 ELSE 1 END,
                (queue_order IS NULL),
                queue_order,
                COALESCE(finished_at, updated_at, started_at) DESC,
                started_at DESC,
                id DESC
            """
        params.append(max(1, min(int(limit or 50), 200)))
        rows = self.db.query(
            f"""
            SELECT *
            FROM task_runs
            {where}
            ORDER BY {order_by}
            LIMIT ?
            """,
            params,
        )
        for row in rows:
            row["summary"] = json.loads(row.pop("summary_json") or "{}")
            row.pop("payload_json", None)
            row.pop("queue_order", None)
        return rows


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


    def analysis_reports(self, per_mode_limit: int = 100) -> Dict[str, Any]:
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
            strategy_name = decoded.get("summary", {}).get("strategy_name") or decoded.get("config", {}).get("name") or "未命名策略"
            reports = groups.setdefault(strategy_name, [])
            if len(reports) < max(1, min(per_mode_limit, 100)):
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
        if not analysis["summary"].get("trade_date"):
            metrics = self.db.scalar("SELECT metrics_json FROM candidate_results WHERE run_id = ? LIMIT 1", [run_id])
            trade_date = json.loads(metrics or "{}").get("bar_date")
            if trade_date:
                analysis["summary"]["trade_date"] = trade_date
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

    def _decode_analysis_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        decoded = dict(row)
        decoded["summary"] = json.loads(decoded.pop("summary_json") or "{}")
        decoded["config"] = json.loads(decoded.pop("config_json") or "{}")
        strategy_name = self._analysis_strategy_name(decoded["summary"], decoded["config"])
        if strategy_name:
            decoded["summary"]["strategy_name"] = strategy_name
            decoded["config"]["strategy_name"] = strategy_name
            decoded["config"]["name"] = strategy_name
            decoded["config"]["preset_name"] = strategy_name
        return decoded

    def _analysis_strategy_name(self, summary: Dict[str, Any], config: Dict[str, Any]) -> str:
        for source in (summary, config):
            for key in ("strategy_name", "name", "preset_name"):
                value = str(source.get(key) or "").strip()
                if value and value != "未命名策略":
                    return value
        return self._strategy_name_from_matching_preset(config) or "未命名策略"

    def _strategy_name_from_matching_preset(self, config: Dict[str, Any]) -> Optional[str]:
        target = _config_signature(config)
        if not target:
            return None
        rows = self.db.query(
            """
            SELECT name, config_json
            FROM strategy_presets
            WHERE deleted_at IS NULL
            ORDER BY is_default DESC, updated_at DESC NULLS LAST, created_at DESC NULLS LAST
            LIMIT 500
            """
        )
        for row in rows:
            try:
                preset_config = json.loads(row.get("config_json") or "{}")
            except json.JSONDecodeError:
                continue
            if _config_signature(preset_config) == target:
                name = str(row.get("name") or "").strip()
                if name:
                    return name
        return None



def _config_signature(config: Dict[str, Any]) -> str:
    if not isinstance(config, dict):
        return ""
    ignored = {"strategy_name", "name", "preset_name", "migration"}

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: clean(item) for key, item in sorted(value.items()) if key not in ignored}
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return json.dumps(clean(config), ensure_ascii=False, sort_keys=True, default=str)
