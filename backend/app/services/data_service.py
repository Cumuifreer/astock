from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.app.db import Database


CAPABILITY_DEFINITIONS = {
    "历史 K 线": {
        "fallback_sources": ["Baostock", "AData", "本地缓存"],
        "can_backfill": True,
        "participates_in_analysis": True,
    },
    "当天行情快照": {
        "fallback_sources": ["AkShare 新浪", "AkShare 腾讯", "AData", "本地缓存"],
        "can_backfill": True,
        "participates_in_analysis": True,
    },
    "股票基础信息": {
        "fallback_sources": ["Baostock", "AData", "AkShare 快照", "本地缓存"],
        "can_backfill": True,
        "participates_in_analysis": True,
    },
    "流通市值": {
        "fallback_sources": ["AkShare 新浪", "AData", "本地缓存"],
        "can_backfill": True,
        "participates_in_analysis": True,
    },
    "换手率": {
        "fallback_sources": ["Baostock", "AkShare 新浪", "本地缓存"],
        "can_backfill": True,
        "participates_in_analysis": True,
    },
    "RPS": {
        "fallback_sources": ["本地历史 K 线"],
        "can_backfill": False,
        "participates_in_analysis": True,
    },
    "振幅": {
        "fallback_sources": ["本地历史 K 线"],
        "can_backfill": False,
        "participates_in_analysis": True,
    },
    "概念标签": {
        "fallback_sources": [],
        "can_backfill": False,
        "participates_in_analysis": False,
    },
    "ST / 停牌状态": {
        "fallback_sources": ["Baostock", "本地缓存"],
        "can_backfill": True,
        "participates_in_analysis": True,
    },
    "市场环境": {
        "fallback_sources": [],
        "can_backfill": False,
        "participates_in_analysis": False,
    },
}


class DataService:
    def __init__(self, db: Database):
        self.db = db

    def overview(self) -> Dict[str, Any]:
        latest_run = self.latest_analysis_run()
        latest_task = self.latest_task("update")
        return {
            "stock_count": self.db.scalar("SELECT COUNT(*) FROM stock_basic") or 0,
            "history_rows": self.db.scalar("SELECT COUNT(*) FROM historical_bars") or 0,
            "snapshot_rows": self.db.scalar("SELECT COUNT(*) FROM daily_snapshots") or 0,
            "latest_history_date": self.db.scalar("SELECT MAX(date) FROM historical_bars"),
            "latest_snapshot_date": self.db.scalar("SELECT MAX(date) FROM daily_snapshots"),
            "turnover_coverage": self._ratio(
                self.db.scalar(
                    """
                    SELECT COUNT(DISTINCT code)
                    FROM historical_bars
                    WHERE turn IS NOT NULL
                      AND date = (SELECT MAX(date) FROM historical_bars)
                    """
                )
                or 0,
                self.db.scalar("SELECT COUNT(*) FROM stock_basic") or 0,
            ),
            "latest_analysis": latest_run,
            "latest_update": latest_task,
            "warnings": self.db.query(
                "SELECT * FROM warnings ORDER BY created_at DESC LIMIT 8"
            ),
        }

    def list_stocks(self, limit: int = 50, offset: int = 0, search: str = "") -> Dict[str, Any]:
        params: List[Any] = []
        where = ""
        if search:
            where = "WHERE code ILIKE ? OR name ILIKE ?"
            params.extend([f"%{search}%", f"%{search}%"])
        total = self.db.scalar(f"SELECT COUNT(*) FROM stock_basic {where}", params) or 0
        rows = self.db.query(
            f"""
            SELECT b.code, b.name, b.exchange, b.list_date, b.source, b.is_st, b.suspended,
                   s.latest_price, s.pct_chg, s.amount, s.volume, s.turnover_rate,
                   f.float_market_value,
                   (SELECT COUNT(*) FROM historical_bars h WHERE h.code = b.code) AS history_days,
                   (SELECT MAX(date) FROM historical_bars h WHERE h.code = b.code) AS latest_history_date
            FROM stock_basic b
            LEFT JOIN daily_snapshots s
              ON s.code = b.code
             AND s.date = (SELECT MAX(date) FROM daily_snapshots)
            LEFT JOIN float_market_values f
              ON f.code = b.code
             AND f.date = (SELECT MAX(date) FROM float_market_values)
            {where}
            ORDER BY b.code
            LIMIT ? OFFSET ?
            """,
            params + [max(1, min(limit, 500)), max(0, offset)],
        )
        return {"rows": rows, "total": total, "limit": limit, "offset": offset}

    def latest_task(self, kind: str) -> Optional[Dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM task_runs WHERE kind = ? ORDER BY started_at DESC LIMIT 1",
            [kind],
        )
        if not rows:
            return None
        row = rows[0]
        row["summary"] = json.loads(row.pop("summary_json") or "{}")
        return row

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
        rows = self.db.query("SELECT * FROM data_capabilities ORDER BY capability")
        if not rows:
            self.refresh_capabilities()
            rows = self.db.query("SELECT * FROM data_capabilities ORDER BY capability")
        for row in rows:
            row["actual_sources"] = json.loads(row.get("actual_sources") or "[]")
            row["fallback_sources"] = json.loads(row.get("fallback_sources") or "[]")
        return rows

    def refresh_capabilities(self) -> None:
        total_stocks = self.db.scalar("SELECT COUNT(*) FROM stock_basic") or 0
        latest_history = self.db.scalar("SELECT MAX(date) FROM historical_bars")
        latest_snapshot = self.db.scalar("SELECT MAX(date) FROM daily_snapshots")
        status_failures = self.db.query(
            """
            SELECT capability, failure_reason
            FROM source_status
            WHERE failure_reason IS NOT NULL
            QUALIFY ROW_NUMBER() OVER (PARTITION BY capability ORDER BY last_checked DESC) = 1
            """
        )
        failure_by_cap = {row["capability"]: row["failure_reason"] for row in status_failures}

        rows = []
        counts = {
            "历史 K 线": self.db.scalar("SELECT COUNT(DISTINCT code) FROM historical_bars") or 0,
            "当天行情快照": self.db.scalar(
                "SELECT COUNT(DISTINCT code) FROM daily_snapshots WHERE date = (SELECT MAX(date) FROM daily_snapshots)"
            )
            or 0,
            "股票基础信息": total_stocks,
            "流通市值": self.db.scalar(
                "SELECT COUNT(DISTINCT code) FROM float_market_values WHERE float_market_value IS NOT NULL"
            )
            or 0,
            "换手率": self.db.scalar("SELECT COUNT(DISTINCT code) FROM historical_bars WHERE turn IS NOT NULL") or 0,
            "RPS": self.db.scalar(
                "SELECT COUNT(*) FROM (SELECT code, COUNT(*) AS n FROM historical_bars GROUP BY code HAVING n >= 21)"
            )
            or 0,
            "振幅": self.db.scalar(
                "SELECT COUNT(DISTINCT code) FROM historical_bars WHERE high IS NOT NULL AND low IS NOT NULL AND prev_close IS NOT NULL"
            )
            or 0,
            "概念标签": 0,
            "ST / 停牌状态": self.db.scalar("SELECT COUNT(DISTINCT code) FROM historical_bars WHERE is_st IS NOT NULL OR tradestatus IS NOT NULL")
            or 0,
            "市场环境": 0,
        }
        source_rows = self.db.query(
            """
            SELECT capability, source
            FROM source_status
            WHERE status IN ('available', 'completed_full', 'completed_partial')
            """
        )
        sources_by_cap: Dict[str, List[str]] = {}
        for row in source_rows:
            sources_by_cap.setdefault(row["capability"], []).append(row["source"])

        for capability, definition in CAPABILITY_DEFINITIONS.items():
            coverage = int(counts.get(capability, 0))
            denominator = total_stocks if total_stocks else coverage
            rows.append(
                {
                    "capability": capability,
                    "actual_sources": sources_by_cap.get(capability, []),
                    "fallback_sources": definition["fallback_sources"],
                    "coverage_count": coverage,
                    "missing_count": max(0, int(denominator) - coverage),
                    "latest_update": latest_snapshot if capability == "当天行情快照" else latest_history,
                    "last_failure_reason": failure_by_cap.get(capability),
                    "uses_cache": True,
                    "can_backfill": definition["can_backfill"],
                    "participates_in_analysis": definition["participates_in_analysis"],
                    "updated_at": datetime.utcnow(),
                }
            )
        self.db.upsert("data_capabilities", rows, ["capability"])

    @staticmethod
    def _ratio(count: int, total: int) -> Dict[str, Any]:
        return {
            "count": count,
            "total": total,
            "percent": round((count / total * 100) if total else 0, 2),
        }
