from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from backend.app.db import Database
from backend.app.services.analysis_service import AnalysisService, apply_strategy_filters
from backend.app.services.market_utils import safe_float
from backend.app.services.strategy_service import normalize_strategy_config
from backend.app.services.update_service import TaskBusy


DEFAULT_STEP = 5
DEFAULT_LOOKBACK_DATES = 120
LABEL_HORIZON = 20


class BacktestService:
    def __init__(self, db: Database, analysis_service: Optional[AnalysisService] = None):
        self.db = db
        self.analysis_service = analysis_service or AnalysisService(db)
        self.executor = ThreadPoolExecutor(max_workers=1)

    def start(self, payload: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
        running = self.db.scalar(
            "SELECT COUNT(*) FROM task_runs WHERE kind = 'backtest' AND status = 'running'"
        )
        if running:
            raise TaskBusy("已有回测正在运行。")
        task_id = f"backtest-{uuid.uuid4().hex[:12]}"
        run_id = f"backtest-{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        config = normalize_strategy_config((payload or {}).get("config") or {})
        self._write_task(
            task_id,
            kind="backtest",
            status="running",
            stage="准备回测",
            source="本地仓库",
            current_stock=None,
            total=0,
            processed=0,
            success=0,
            failed=0,
            skipped=0,
            warning=None,
            summary={"backtest_run_id": run_id},
            error_message=None,
            started_at=now,
        )
        self.db.upsert(
            "backtest_runs",
            [
                {
                    "id": run_id,
                    "status": "running",
                    "started_at": now,
                    "finished_at": None,
                    "config_json": json.dumps(config, ensure_ascii=False),
                    "summary_json": "{}",
                    "error_message": None,
                }
            ],
            ["id"],
        )
        self.executor.submit(self.run, payload or {}, run_id, task_id)
        return task_id, run_id

    def run(self, payload: Dict[str, Any], run_id: Optional[str] = None, task_id: Optional[str] = None) -> str:
        run_id = run_id or f"backtest-{uuid.uuid4().hex[:12]}"
        started_at = datetime.utcnow()
        if not self.db.scalar("SELECT COUNT(*) FROM backtest_runs WHERE id = ?", [run_id]):
            self.db.upsert(
                "backtest_runs",
                [
                    {
                        "id": run_id,
                        "status": "running",
                        "started_at": started_at,
                        "finished_at": None,
                        "config_json": "{}",
                        "summary_json": "{}",
                        "error_message": None,
                    }
                ],
                ["id"],
            )
        try:
            strategy, sampled_dates, options = self._resolve_options(payload)
            self._update_run(run_id, status="running", config=strategy)
            if task_id:
                self._patch_task(
                    task_id,
                    stage="读取本地历史",
                    total=len(sampled_dates),
                    processed=0,
                    summary={"backtest_run_id": run_id, **options},
                )

            label_bars = pd.DataFrame(
                self.db.query(
                    """
                    SELECT code, date, open, high, low, close
                    FROM historical_bars
                    WHERE date >= ?
                    ORDER BY code, date
                    """,
                    [_date_value(options["start_date"])],
                )
            )
            history_by_code = {
                str(code): group.copy()
                for code, group in label_bars.groupby("code")
            } if not label_bars.empty else {}

            self.db.execute("DELETE FROM backtest_signals WHERE run_id = ?", [run_id], write=True)
            signal_rows: List[Dict[str, Any]] = []
            failed_dates = 0
            zero_signal_dates = 0
            signal_dates = 0
            last_warning = None

            for index, as_of in enumerate(sampled_dates, start=1):
                if task_id:
                    self._patch_task(
                        task_id,
                        stage="回放历史信号",
                        current_stock=as_of.isoformat(),
                        processed=index - 1,
                    )
                try:
                    frame = self.analysis_service._build_analysis_frame(strategy, as_of_date=as_of)
                    candidates, _, _ = apply_strategy_filters(frame, strategy)
                    if not candidates:
                        zero_signal_dates += 1
                    else:
                        signal_dates += 1
                    for rank, candidate in enumerate(candidates, start=1):
                        labels = compute_forward_labels(
                            history_by_code.get(str(candidate.get("code")), pd.DataFrame()),
                            str(candidate.get("code")),
                            as_of,
                        )
                        signal_rows.append(
                            {
                                "run_id": run_id,
                                "as_of_date": as_of,
                                "rank": rank,
                                "code": candidate.get("code"),
                                "name": candidate.get("name"),
                                "latest_price": safe_float(candidate.get("latest_price")),
                                "signal_type": candidate.get("signal_type"),
                                "signal_score": safe_float(candidate.get("signal_score")),
                                "reasons_json": json.dumps(candidate.get("reasons") or [], ensure_ascii=False),
                                "metrics_json": json.dumps(_jsonable(candidate), ensure_ascii=False),
                                "created_at": datetime.utcnow(),
                                **labels,
                            }
                        )
                except Exception as exc:
                    failed_dates += 1
                    last_warning = f"{as_of.isoformat()} 回测失败：{exc}"
                if task_id:
                    self._patch_task(
                        task_id,
                        current_stock=as_of.isoformat(),
                        processed=index,
                        success=signal_dates,
                        failed=failed_dates,
                        skipped=zero_signal_dates,
                        warning=last_warning,
                    )

            self.db.upsert("backtest_signals", signal_rows, ["run_id", "as_of_date", "code"])
            summary = summarize_backtest(signal_rows, sampled_dates, failed_dates, zero_signal_dates, options)
            status = "completed_partial" if failed_dates else "completed_full"
            self._update_run(
                run_id,
                status=status,
                finished_at=datetime.utcnow(),
                config=strategy,
                summary=summary,
                error_message=None,
            )
            if task_id:
                self._patch_task(
                    task_id,
                    status=status,
                    stage="回测完成" if status == "completed_full" else "部分完成",
                    current_stock=None,
                    total=len(sampled_dates),
                    processed=len(sampled_dates),
                    success=signal_dates,
                    failed=failed_dates,
                    skipped=zero_signal_dates,
                    warning=last_warning,
                    summary={"backtest_run_id": run_id, **summary},
                    finished_at=datetime.utcnow(),
                )
        except Exception as exc:
            self._update_run(
                run_id,
                status="failed",
                finished_at=datetime.utcnow(),
                error_message=str(exc),
            )
            if task_id:
                self._patch_task(
                    task_id,
                    status="failed",
                    stage="回测失败",
                    failed=1,
                    warning=str(exc),
                    error_message=str(exc),
                    finished_at=datetime.utcnow(),
                )
            raise
        return run_id

    def _resolve_options(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], List[date], Dict[str, Any]]:
        dates = [
            _date_value(row["date"])
            for row in self.db.query("SELECT DISTINCT date FROM historical_bars ORDER BY date")
        ]
        dates = [item for item in dates if item is not None]
        if not dates:
            raise RuntimeError("本地仓库暂无历史 K 线，无法回测。")

        end_request = _date_value(payload.get("end_date"))
        if end_request:
            end_candidates = [item for item in dates if item <= end_request]
            if not end_candidates:
                raise RuntimeError("回测结束日期早于本地历史数据。")
            end_date = end_candidates[-1]
            end_index = dates.index(end_date)
        else:
            end_index = max(0, len(dates) - LABEL_HORIZON - 1)
            end_date = dates[end_index]

        start_request = _date_value(payload.get("start_date"))
        start_date = start_request or dates[max(0, end_index - DEFAULT_LOOKBACK_DATES)]
        if start_date > end_date:
            raise RuntimeError("回测开始日期不能晚于结束日期。")

        step = int(safe_float(payload.get("step")) or DEFAULT_STEP)
        step = max(1, min(step, 60))
        sampled_dates = [item for item in dates if start_date <= item <= end_date][::step]
        if not sampled_dates:
            raise RuntimeError("当前日期范围内没有可回测交易日。")

        strategy = normalize_strategy_config(payload.get("config") or {})
        candidate_limit = safe_float(payload.get("candidate_limit"))
        if candidate_limit is not None and candidate_limit > 0:
            strategy["candidate_limit"] = int(max(1, min(candidate_limit, 500)))

        options = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "step": step,
            "sampled_dates": len(sampled_dates),
            "label_horizon": LABEL_HORIZON,
            "entry_rule": "next_open",
        }
        return strategy, sampled_dates, options

    def _update_run(
        self,
        run_id: str,
        status: str,
        finished_at: Optional[datetime] = None,
        config: Optional[Dict[str, Any]] = None,
        summary: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> None:
        current = self.db.query("SELECT * FROM backtest_runs WHERE id = ?", [run_id])
        row = current[0] if current else {"id": run_id, "started_at": datetime.utcnow()}
        row.update(
            {
                "status": status,
                "finished_at": finished_at,
                "config_json": json.dumps(config, ensure_ascii=False) if config is not None else row.get("config_json", "{}"),
                "summary_json": json.dumps(summary, ensure_ascii=False) if summary is not None else row.get("summary_json", "{}"),
                "error_message": error_message,
            }
        )
        self.db.upsert("backtest_runs", [row], ["id"])

    def _write_task(self, task_id: str, **values: Any) -> None:
        now = datetime.utcnow()
        self.db.upsert(
            "task_runs",
            [
                {
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
                    "cancel_requested": False,
                    "started_at": values.get("started_at") or now,
                    "updated_at": now,
                    "finished_at": values.get("finished_at"),
                    "error_message": values.get("error_message"),
                }
            ],
            ["id"],
        )

    def _patch_task(self, task_id: str, **changes: Any) -> None:
        current = self.db.query("SELECT * FROM task_runs WHERE id = ?", [task_id])
        if not current:
            return
        row = current[0]
        summary = changes.pop("summary", None)
        if summary is not None:
            changes["summary_json"] = json.dumps(summary, ensure_ascii=False)
        changes["updated_at"] = datetime.utcnow()
        self.db.upsert("task_runs", [{**row, **changes}], ["id"])


def compute_forward_labels(bars: pd.DataFrame, code: str, as_of_date: date) -> Dict[str, Any]:
    target = _date_value(as_of_date)
    empty = {
        "entry_date": None,
        "entry_price": None,
        "return_5d": None,
        "return_10d": None,
        "return_20d": None,
        "max_return_10d": None,
        "max_drawdown_10d": None,
        "hit_5pct_10d": None,
        "hit_8pct_10d": None,
        "hit_stop_5pct_10d": None,
    }
    if target is None or bars.empty:
        return empty
    frame = bars.copy()
    if "code" in frame:
        frame = frame[frame["code"] == code]
    if frame.empty:
        return empty
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
    frame = frame.dropna(subset=["date"]).sort_values("date")
    future = frame[frame["date"] > target].copy()
    if future.empty:
        return empty

    entry = future.iloc[0]
    entry_price = safe_float(entry.get("open")) or safe_float(entry.get("close"))
    if entry_price is None or entry_price <= 0:
        return empty

    def horizon_return(days: int) -> Optional[float]:
        if len(future) < days:
            return None
        close_value = safe_float(future.iloc[days - 1].get("close"))
        if close_value is None:
            return None
        return round(close_value / entry_price - 1, 6)

    window10 = future.head(10)
    max_return_10d = None
    max_drawdown_10d = None
    if len(window10) >= 10:
        high = safe_float(pd.to_numeric(window10["high"], errors="coerce").max())
        low = safe_float(pd.to_numeric(window10["low"], errors="coerce").min())
        if high is not None:
            max_return_10d = round(high / entry_price - 1, 6)
        if low is not None:
            max_drawdown_10d = round(low / entry_price - 1, 6)

    return {
        "entry_date": _date_value(entry.get("date")),
        "entry_price": round(entry_price, 6),
        "return_5d": horizon_return(5),
        "return_10d": horizon_return(10),
        "return_20d": horizon_return(20),
        "max_return_10d": max_return_10d,
        "max_drawdown_10d": max_drawdown_10d,
        "hit_5pct_10d": max_return_10d >= 0.05 if max_return_10d is not None else None,
        "hit_8pct_10d": max_return_10d >= 0.08 if max_return_10d is not None else None,
        "hit_stop_5pct_10d": max_drawdown_10d <= -0.05 if max_drawdown_10d is not None else None,
    }


def summarize_backtest(
    signal_rows: List[Dict[str, Any]],
    sampled_dates: List[date],
    failed_dates: int,
    zero_signal_dates: int,
    options: Dict[str, Any],
) -> Dict[str, Any]:
    signal_count = len(signal_rows)
    return {
        **options,
        "evaluated_dates": len(sampled_dates),
        "signal_dates": len({row["as_of_date"] for row in signal_rows}),
        "zero_signal_dates": zero_signal_dates,
        "failed_dates": failed_dates,
        "signal_count": signal_count,
        "avg_return_5d": _avg(signal_rows, "return_5d"),
        "avg_return_10d": _avg(signal_rows, "return_10d"),
        "avg_return_20d": _avg(signal_rows, "return_20d"),
        "median_return_10d": _median(signal_rows, "return_10d"),
        "median_max_drawdown_10d": _median(signal_rows, "max_drawdown_10d"),
        "hit_5pct_10d_rate": _rate(signal_rows, "hit_5pct_10d"),
        "hit_8pct_10d_rate": _rate(signal_rows, "hit_8pct_10d"),
        "hit_stop_5pct_10d_rate": _rate(signal_rows, "hit_stop_5pct_10d"),
        "label_20d_coverage": _coverage(signal_rows, "return_20d"),
    }


def _avg(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = [safe_float(row.get(key)) for row in rows]
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 6)


def _median(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = sorted(value for value in (safe_float(row.get(key)) for row in rows) if value is not None)
    if not values:
        return None
    midpoint = len(values) // 2
    if len(values) % 2:
        return round(values[midpoint], 6)
    return round((values[midpoint - 1] + values[midpoint]) / 2, 6)


def _rate(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    values = [row.get(key) for row in rows if row.get(key) is not None]
    if not values:
        return None
    return round(sum(1 for value in values if value) / len(values), 6)


def _coverage(rows: List[Dict[str, Any]], key: str) -> Optional[float]:
    if not rows:
        return None
    return round(sum(1 for row in rows if row.get(key) is not None) / len(rows), 6)


def _date_value(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _jsonable(row: Dict[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
            clean[key] = value
            continue
        try:
            if pd.isna(value):
                clean[key] = None
                continue
        except ValueError:
            pass
        clean[key] = str(value)
    return clean
