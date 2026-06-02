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

        label_safe_index = max(0, len(dates) - LABEL_HORIZON - 1)
        requested_end_date = None
        end_date_adjusted = False
        end_request = _date_value(payload.get("end_date"))
        if end_request:
            end_candidates = [item for item in dates if item <= end_request]
            if not end_candidates:
                raise RuntimeError("回测结束日期早于本地历史数据。")
            requested_end_date = end_request.isoformat()
            requested_end_index = dates.index(end_candidates[-1])
            end_index = min(requested_end_index, label_safe_index)
            end_date_adjusted = end_index < requested_end_index
            end_date = dates[end_index]
        else:
            end_index = label_safe_index
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
        float_policy = str(payload.get("float_market_value_policy") or "strategy")
        if float_policy not in {"strategy", "allow_missing", "latest_proxy"}:
            float_policy = "strategy"
        if float_policy == "allow_missing":
            strategy["missing_float_market_value_policy"] = "allow"
        if float_policy == "latest_proxy":
            strategy["_backtest_float_market_value_policy"] = "latest_proxy"
        candidate_limit = safe_float(payload.get("candidate_limit"))
        if candidate_limit is not None and candidate_limit > 0:
            strategy["candidate_limit"] = int(max(1, min(candidate_limit, 500)))

        options = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "step": step,
            "sampled_dates": len(sampled_dates),
            "label_horizon": LABEL_HORIZON,
            "requested_end_date": requested_end_date,
            "end_date_adjusted_for_label_horizon": end_date_adjusted,
            "entry_rule": "next_open",
            "float_market_value_policy": float_policy,
        }
        return strategy, sampled_dates, options

    def run_signal_evaluation(
        self,
        payload: Dict[str, Any],
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        run_id = run_id or f"signal-eval-{uuid.uuid4().hex[:12]}"
        self.run(payload, run_id=run_id, task_id=task_id)
        run = self.db.query("SELECT * FROM backtest_runs WHERE id = ?", [run_id])[0]
        signals = self._signals_for_run(run_id, limit=5000)
        summary = json.loads(run.get("summary_json") or "{}")
        summary.update(_signal_diagnostics(signals))
        self._update_run(
            run_id,
            status=run.get("status") or "completed_full",
            finished_at=run.get("finished_at"),
            config=json.loads(run.get("config_json") or "{}"),
            summary=summary,
            error_message=run.get("error_message"),
        )
        run = self.db.query("SELECT * FROM backtest_runs WHERE id = ?", [run_id])[0]
        if task_id:
            self._patch_task(
                task_id,
                summary={"backtest_run_id": run_id, **summary},
                stage="信号评估完成",
            )
        return {"run": self._decode_run_row(run), "signals": signals}

    def run_portfolio_backtest(
        self,
        payload: Dict[str, Any],
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        run_id = run_id or f"portfolio-{uuid.uuid4().hex[:12]}"
        started_at = datetime.utcnow()
        try:
            strategy, sampled_dates, options = self._resolve_options(payload)
            hold_days = int(payload.get("hold_days") or 5)
            max_positions = int(payload.get("max_positions") or payload.get("candidate_limit") or 5)
            transaction_cost = (safe_float(payload.get("transaction_cost_bps")) or 0) / 10000
            slippage = (safe_float(payload.get("slippage_bps")) or 0) / 10000
            initial_equity = _resolve_initial_equity(payload)
            run_config = {**payload, "initial_equity": initial_equity, "config": strategy}
            equity = initial_equity
            peak = initial_equity
            trades: List[Dict[str, Any]] = []
            equity_rows: List[Dict[str, Any]] = []
            self.db.upsert(
                "portfolio_backtest_runs",
                [
                    {
                        "id": run_id,
                        "status": "running",
                        "started_at": started_at,
                        "finished_at": None,
                        "config_json": json.dumps(run_config, ensure_ascii=False),
                        "summary_json": json.dumps(options, ensure_ascii=False),
                        "error_message": None,
                    }
                ],
                ["id"],
            )
            if task_id:
                self._patch_task(
                    task_id,
                    stage="组合回测",
                    total=len(sampled_dates),
                    processed=0,
                    summary={"backtest_run_id": run_id, **options},
                )
            all_bars = pd.DataFrame(
                self.db.query(
                    """
                    SELECT code, date, open, high, low, close, prev_close, pct_chg, is_st
                    FROM historical_bars
                    WHERE date >= ?
                    ORDER BY code, date
                    """,
                    [_date_value(options["start_date"])],
                )
            )
            bars_by_code = {str(code): group.copy() for code, group in all_bars.groupby("code")} if not all_bars.empty else {}
            for index, as_of in enumerate(sampled_dates, start=1):
                try:
                    frame = self.analysis_service._build_analysis_frame(strategy, as_of_date=as_of)
                    candidates, _, _ = apply_strategy_filters(frame, strategy)
                except Exception:
                    candidates = []
                for candidate in candidates[:max_positions]:
                    code = str(candidate.get("code"))
                    trade = _simulate_trade(
                        bars_by_code.get(code, pd.DataFrame()),
                        code,
                        candidate.get("name") or code,
                        as_of,
                        hold_days,
                        transaction_cost,
                        slippage,
                    )
                    if trade:
                        trade["run_id"] = run_id
                        trade["trade_id"] = f"{as_of.isoformat()}:{code}"
                        trade["weight"] = 1 / max(1, max_positions)
                        trade["payload_json"] = json.dumps({"signal_score": candidate.get("signal_score")}, ensure_ascii=False)
                        trades.append(trade)
                period_returns = [safe_float(trade.get("return_pct")) for trade in trades if trade.get("entry_signal_date") == as_of]
                clean_returns = [value for value in period_returns if value is not None]
                if clean_returns:
                    equity *= 1 + sum(clean_returns) / len(clean_returns)
                peak = max(peak, equity)
                equity_rows.append(
                    {
                        "run_id": run_id,
                        "trade_date": as_of,
                        "equity": round(equity, 4),
                        "cash": round(equity, 4),
                        "position_value": 0.0,
                        "drawdown": round(equity / peak - 1, 6) if peak else 0,
                    }
                )
                if task_id:
                    self._patch_task(task_id, processed=index, success=len(trades), current_stock=as_of.isoformat())
            summary = _portfolio_summary(initial_equity, equity, trades, equity_rows, options)
            now = datetime.utcnow()
            self.db.upsert(
                "portfolio_backtest_runs",
                [
                    {
                        "id": run_id,
                        "status": "completed_full",
                        "started_at": started_at,
                        "finished_at": now,
                        "config_json": json.dumps(run_config, ensure_ascii=False),
                        "summary_json": json.dumps(summary, ensure_ascii=False),
                        "error_message": None,
                    }
                ],
                ["id"],
            )
            self.db.upsert("portfolio_backtest_trades", [_trade_row(trade) for trade in trades], ["run_id", "trade_id"])
            self.db.upsert("portfolio_backtest_equity", equity_rows, ["run_id", "trade_date"])
            if task_id:
                self._patch_task(
                    task_id,
                    status="completed_full",
                    stage="组合回测完成",
                    current_stock=None,
                    total=len(sampled_dates),
                    processed=len(sampled_dates),
                    success=len(trades),
                    summary={"backtest_run_id": run_id, **summary},
                    finished_at=now,
                )
            return {
                "run": {
                    "id": run_id,
                    "status": "completed_full",
                    "started_at": started_at,
                    "finished_at": now,
                    "summary": summary,
                    "config": run_config,
                    "error_message": None,
                },
                "trades": [_jsonable(trade) for trade in trades],
                "equity_curve": equity_rows,
            }
        except Exception as exc:
            now = datetime.utcnow()
            self.db.upsert(
                "portfolio_backtest_runs",
                [
                    {
                        "id": run_id,
                        "status": "failed",
                        "started_at": started_at,
                        "finished_at": now,
                        "config_json": json.dumps(payload or {}, ensure_ascii=False),
                        "summary_json": "{}",
                        "error_message": str(exc),
                    }
                ],
                ["id"],
            )
            if task_id:
                self._patch_task(
                    task_id,
                    status="failed",
                    stage="组合回测失败",
                    failed=1,
                    warning=str(exc),
                    error_message=str(exc),
                    finished_at=now,
                )
            raise

    def portfolio_result(self, run_id: str) -> Dict[str, Any]:
        rows = self.db.query("SELECT * FROM portfolio_backtest_runs WHERE id = ?", [run_id])
        if not rows:
            return {"run": None, "trades": [], "equity_curve": []}
        run = rows[0]
        return {
            "run": {
                **run,
                "summary": json.loads(run.pop("summary_json") or "{}"),
                "config": json.loads(run.pop("config_json") or "{}"),
            },
            "trades": self.db.query("SELECT * FROM portfolio_backtest_trades WHERE run_id = ? ORDER BY entry_date, code", [run_id]),
            "equity_curve": self.db.query("SELECT * FROM portfolio_backtest_equity WHERE run_id = ? ORDER BY trade_date", [run_id]),
        }

    def _signals_for_run(self, run_id: str, limit: int = 5000) -> List[Dict[str, Any]]:
        rows = self.db.query(
            """
            SELECT *
            FROM backtest_signals
            WHERE run_id = ?
            ORDER BY as_of_date, rank
            LIMIT ?
            """,
            [run_id, limit],
        )
        for row in rows:
            row["reasons"] = json.loads(row.pop("reasons_json") or "[]")
            row["metrics"] = json.loads(row.pop("metrics_json") or "{}")
        return rows

    @staticmethod
    def _decode_run_row(row: Dict[str, Any]) -> Dict[str, Any]:
        decoded = dict(row)
        decoded["summary"] = json.loads(decoded.pop("summary_json") or "{}")
        decoded["config"] = json.loads(decoded.pop("config_json") or "{}")
        return decoded

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


def _signal_diagnostics(signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not signals:
        return {
            "rank_ic": None,
            "ic": None,
            "top_n_avg_return_10d": None,
            "bucket_monotonicity": None,
            "resonance_hit_avg_return_10d": None,
        }
    returns = [safe_float(row.get("return_10d")) for row in signals]
    scores = [safe_float(row.get("signal_score")) for row in signals]
    pairs = [(score, ret) for score, ret in zip(scores, returns) if score is not None and ret is not None]
    rank_ic = _correlation([_rank(score, [p[0] for p in pairs]) for score, _ in pairs], [_rank(ret, [p[1] for p in pairs]) for _, ret in pairs]) if len(pairs) >= 3 else None
    ic = _correlation([score for score, _ in pairs], [ret for _, ret in pairs]) if len(pairs) >= 3 else None
    top = sorted(pairs, key=lambda item: item[0], reverse=True)[: min(20, len(pairs))]
    top_avg = round(sum(ret for _, ret in top) / len(top), 6) if top else None
    buckets = _score_buckets(pairs)
    monotonic = None
    if len(buckets) >= 2:
        bucket_returns = [bucket["avg_return_10d"] for bucket in buckets if bucket["avg_return_10d"] is not None]
        monotonic = all(bucket_returns[index] <= bucket_returns[index + 1] for index in range(len(bucket_returns) - 1))
    resonance_rows = [
        row
        for row in signals
        if (row.get("metrics") or {}).get("score_breakdown", {}).get("resonance_bonus")
    ]
    return {
        "rank_ic": rank_ic,
        "ic": ic,
        "top_n_avg_return_10d": top_avg,
        "score_buckets": buckets,
        "bucket_monotonicity": monotonic,
        "resonance_hit_count": len(resonance_rows),
        "resonance_hit_avg_return_10d": _avg(resonance_rows, "return_10d"),
    }


def _simulate_trade(
    bars: pd.DataFrame,
    code: str,
    name: str,
    as_of: date,
    hold_days: int,
    transaction_cost: float,
    slippage: float,
) -> Optional[Dict[str, Any]]:
    if bars.empty:
        return None
    frame = bars.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce").dt.date
    frame = frame.dropna(subset=["date"]).sort_values("date")
    future = frame[frame["date"] > as_of].copy()
    if future.empty:
        return None
    entry = future.iloc[0]
    entry_open = safe_float(entry.get("open")) or safe_float(entry.get("close"))
    entry_prev = safe_float(entry.get("close"))
    if entry_open is None or entry_open <= 0:
        return None
    if _likely_limit_up(entry):
        return None
    exit_index = min(max(1, hold_days) - 1, len(future) - 1)
    exit_row = future.iloc[exit_index]
    exit_price = safe_float(exit_row.get("close")) or safe_float(exit_row.get("open"))
    exit_date = _date_value(exit_row.get("date"))
    while exit_price is not None and _likely_limit_down(exit_row) and exit_index + 1 < len(future):
        exit_index += 1
        exit_row = future.iloc[exit_index]
        exit_price = safe_float(exit_row.get("close")) or safe_float(exit_row.get("open"))
        exit_date = _date_value(exit_row.get("date"))
    if exit_price is None or exit_price <= 0 or exit_date is None:
        return None
    adjusted_entry = entry_open * (1 + slippage)
    adjusted_exit = exit_price * (1 - slippage)
    return_pct = adjusted_exit / adjusted_entry - 1 - transaction_cost * 2
    return {
        "entry_signal_date": as_of,
        "code": code,
        "name": name,
        "entry_date": _date_value(entry.get("date")),
        "entry_price": round(adjusted_entry, 6),
        "exit_date": exit_date,
        "exit_price": round(adjusted_exit, 6),
        "shares": 0,
        "return_pct": round(return_pct, 6),
        "exit_reason": "hold_days",
    }


def _portfolio_summary(
    initial_equity: float,
    ending_equity: float,
    trades: List[Dict[str, Any]],
    equity_rows: List[Dict[str, Any]],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    returns = [safe_float(trade.get("return_pct")) for trade in trades]
    clean = [value for value in returns if value is not None]
    max_drawdown = min([safe_float(row.get("drawdown")) or 0 for row in equity_rows] or [0])
    total_return = ending_equity / initial_equity - 1 if initial_equity else 0
    return {
        **options,
        "initial_equity": initial_equity,
        "ending_equity": round(ending_equity, 4),
        "total_return": round(total_return, 6),
        "max_drawdown": round(max_drawdown, 6),
        "trade_count": len(trades),
        "win_rate": round(sum(1 for value in clean if value > 0) / len(clean), 6) if clean else None,
        "avg_trade_return": round(sum(clean) / len(clean), 6) if clean else None,
        "turnover_rate": len(trades) / max(1, len(equity_rows)),
    }


def _resolve_initial_equity(payload: Dict[str, Any]) -> float:
    value = safe_float(payload.get("initial_equity"))
    if value is None:
        value = safe_float(payload.get("initial_capital"))
    if value is None or value <= 0:
        return 1_000_000.0
    return value


def _trade_row(trade: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "run_id": trade["run_id"],
        "trade_id": trade["trade_id"],
        "code": trade["code"],
        "name": trade["name"],
        "entry_date": trade["entry_date"],
        "entry_price": trade["entry_price"],
        "exit_date": trade["exit_date"],
        "exit_price": trade["exit_price"],
        "shares": trade.get("shares"),
        "weight": trade.get("weight"),
        "return_pct": trade.get("return_pct"),
        "exit_reason": trade.get("exit_reason"),
        "payload_json": trade.get("payload_json") or "{}",
    }


def _likely_limit_up(row: pd.Series) -> bool:
    open_price = safe_float(row.get("open"))
    prev_close = safe_float(row.get("prev_close"))
    low = safe_float(row.get("low"))
    if open_price is None or prev_close is None or prev_close <= 0:
        return False
    return open_price / prev_close - 1 >= 0.095 and low >= open_price * 0.999


def _likely_limit_down(row: pd.Series) -> bool:
    open_price = safe_float(row.get("open"))
    prev_close = safe_float(row.get("prev_close"))
    high = safe_float(row.get("high"))
    if open_price is None or prev_close is None or prev_close <= 0:
        return False
    return open_price / prev_close - 1 <= -0.095 and high <= open_price * 1.001


def _correlation(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    x_avg = sum(xs) / len(xs)
    y_avg = sum(ys) / len(ys)
    numerator = sum((x - x_avg) * (y - y_avg) for x, y in zip(xs, ys))
    x_den = sum((x - x_avg) ** 2 for x in xs) ** 0.5
    y_den = sum((y - y_avg) ** 2 for y in ys) ** 0.5
    if not x_den or not y_den:
        return None
    return round(numerator / (x_den * y_den), 6)


def _rank(value: float, values: List[float]) -> float:
    ordered = sorted(values)
    return (ordered.index(value) + 1) / len(ordered)


def _score_buckets(pairs: List[Tuple[float, float]]) -> List[Dict[str, Any]]:
    if not pairs:
        return []
    ordered = sorted(pairs, key=lambda item: item[0])
    bucket_count = min(5, len(ordered))
    buckets = []
    for index in range(bucket_count):
        chunk = ordered[index::bucket_count]
        returns = [ret for _, ret in chunk]
        buckets.append(
            {
                "bucket": index + 1,
                "count": len(chunk),
                "avg_score": round(sum(score for score, _ in chunk) / len(chunk), 6),
                "avg_return_10d": round(sum(returns) / len(returns), 6) if returns else None,
            }
        )
    return buckets


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
