from __future__ import annotations

import ctypes
import gc
import json
import hashlib
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo


from backend.app.config import settings
from backend.app.db import Database
from backend.app.services.data_service import DataService
from backend.app.sources.baostock_source import BaostockSource
from backend.app.sources.base import SourceGuard, SourceUnavailable

CHINA_TZ = ZoneInfo("Asia/Shanghai")
HISTORY_CLOSE_HOUR = 16
logger = logging.getLogger(__name__)


def _task_payload_fingerprint(payload: Dict[str, Any]) -> str:
    comparable = {
        key: value
        for key, value in (payload or {}).items()
        if key != "run_id"
    }
    return json.dumps(
        comparable,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _task_payload_hash(payload: Dict[str, Any]) -> str:
    return hashlib.sha256(_task_payload_fingerprint(payload).encode("utf-8")).hexdigest()


class TaskBusy(RuntimeError):
    pass


class UpdateService:
    def __init__(self, db: Database):
        self.db = db
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.data_service = DataService(db)
        self.analysis_runner: Any = None
        self.strategy_service: Any = None
        self._queue_lock = threading.RLock()
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

    def configure_runners(self, analysis_runner: Any = None, strategy_service: Any = None) -> None:
        self.analysis_runner = analysis_runner
        self.strategy_service = strategy_service

    def close(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

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
        self.db.execute(
            """
            UPDATE analysis_runs
            SET status = 'failed',
                finished_at = ?,
                error_message = '服务重启后中止'
            WHERE status = 'running'
              AND NOT EXISTS (
                  SELECT 1
                  FROM task_runs
                  WHERE task_runs.id = analysis_runs.task_id
                    AND task_runs.status IN ('queued', 'running')
              )
            """,
            [now],
            write=True,
        )
        self.db.execute(
            """
            UPDATE backtest_runs
            SET status = 'failed',
                finished_at = ?,
                error_message = '服务重启后中止'
            WHERE status = 'running'
            """,
            [now],
            write=True,
        )
        self.db.execute(
            """
            UPDATE portfolio_backtest_runs
            SET status = 'failed',
                finished_at = ?,
                error_message = '服务重启后中止'
            WHERE status = 'running'
            """,
            [now],
            write=True,
        )
        self.db.execute(
            """
            UPDATE candidate_ai_summaries
            SET status = 'failed',
                error_message = '服务重启后中止',
                updated_at = ?
            WHERE status IN ('queued', 'running')
              AND NOT EXISTS (
                  SELECT 1
                  FROM task_runs
                  WHERE task_runs.id = candidate_ai_summaries.task_id
                    AND task_runs.status IN ('queued', 'running')
              )
            """,
            [now],
            write=True,
        )


    def kick_queue(self) -> None:
        self._ensure_queue_worker()


    def _release_task_memory(self) -> None:
        gc.collect()
        if os.name != "posix":
            return
        try:
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:
            return

    def start_update(self, options: Optional[Dict[str, Any]] = None) -> str:
        payload = options or {}
        with self._queue_lock:
            existing_rows = self.db.query(
                """
                SELECT id
                FROM task_runs
                WHERE kind = 'update'
                  AND status IN ('queued', 'running')
                ORDER BY started_at, id
                LIMIT 1
                """
            )
            existing = existing_rows[0] if existing_rows else None
            if existing:
                return str(existing["id"])
            task_id = f"update-{uuid.uuid4().hex[:12]}"
            self._enqueue_task(
                task_id,
                kind="update",
                stage="准备更新",
                source=None,
                summary={},
                payload=payload,
            )
            return task_id

    def start_scheduled_daily_update(self, scheduled_at: datetime, mode: str = "daily_light") -> Optional[str]:
        slot = scheduled_at.replace(second=0, microsecond=0)
        task_id = f"update-auto-{slot:%Y%m%d-%H%M}"
        if self.db.scalar("SELECT id FROM task_runs WHERE id = ?", [task_id]):
            return None
        existing = self.db.scalar(
            """
            SELECT id
            FROM task_runs
            WHERE kind = 'update'
              AND status IN ('queued', 'running')
            ORDER BY started_at
            LIMIT 1
            """
        )
        if existing:
            return None
        schedule_key = slot.strftime("%Y-%m-%d %H:%M")
        payload = {
            "mode": mode or "daily_light",
            "scheduled": True,
            "schedule_key": schedule_key,
            "update_date": slot.date().isoformat(),
        }
        self._enqueue_task(
            task_id,
            kind="update",
            stage="准备轻量日更" if payload["mode"] == "daily_light" else "准备定时更新",
            source="Baostock",
            summary={"scheduled": True, "schedule_key": schedule_key, "mode": payload["mode"]},
            payload=payload,
        )
        return task_id

    def start_analysis(self, config: Dict[str, Any], analysis_runner: Any) -> tuple[str, str]:
        self.analysis_runner = analysis_runner
        frozen_config = json.loads(json.dumps(config, ensure_ascii=False))
        with self._queue_lock:
            existing = self._active_task_for_payload("analyze", {"config": frozen_config})
            if existing:
                existing_payload = json.loads(existing.get("payload_json") or "{}")
                existing_summary = json.loads(existing.get("summary_json") or "{}")
                run_id = existing_payload.get("run_id") or existing_summary.get("analysis_run_id") or ""
                return str(existing["id"]), str(run_id)
            task_id = f"analyze-{uuid.uuid4().hex[:12]}"
            run_id = f"analysis-{uuid.uuid4().hex[:12]}"
            self._enqueue_task(
                task_id,
                kind="analyze",
                stage="准备分析",
                source="本地仓库",
                summary={"analysis_run_id": run_id},
                payload={"config": frozen_config, "run_id": run_id},
            )
            return task_id, run_id


    def _active_task_for_payload(self, kind: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        target_hash = _task_payload_hash(payload)
        rows = self.db.query(
            """
            SELECT id, payload_json, summary_json
            FROM task_runs
            WHERE kind = ?
              AND status IN ('queued', 'running')
              AND payload_hash = ?
            ORDER BY started_at, id
            LIMIT 1
            """,
            [kind, target_hash],
        )
        if rows:
            return rows[0]
        target = _task_payload_fingerprint(payload)
        rows = self.db.query(
            """
            SELECT id, payload_json, summary_json
            FROM task_runs
            WHERE kind = ?
              AND status IN ('queued', 'running')
              AND (payload_hash IS NULL OR payload_hash = '')
            ORDER BY started_at, id
            """,
            [kind],
        )
        for row in rows:
            existing_payload = json.loads(row.get("payload_json") or "{}")
            if _task_payload_fingerprint(existing_payload) == target:
                return row
        return None


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
        worker_failed = False
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
                finally:
                    self._release_task_memory()
                self._complete_if_still_running(task_id)
        except Exception:
            worker_failed = True
            logger.exception("任务队列 worker 异常")
        finally:
            with self._queue_lock:
                self._queue_worker_active = False
            if not worker_failed and self.db.scalar("SELECT COUNT(*) FROM task_runs WHERE status = 'queued'"):
                self._ensure_queue_worker()

    def _next_queued_task(self) -> Optional[Dict[str, Any]]:
        with self.db._write_lock:
            with self.db.connect() as conn:
                conn.execute("BEGIN TRANSACTION")
                try:
                    now = datetime.utcnow()
                    queued = conn.execute(
                        """
                        SELECT id
                        FROM task_runs
                        WHERE status = 'queued'
                        ORDER BY (queue_order IS NULL), queue_order, started_at, id
                        LIMIT 1
                        """
                    ).fetchone()
                    if not queued:
                        conn.execute("COMMIT")
                        return None
                    task_id = str(queued[0])
                    conn.execute(
                        """
                        UPDATE task_runs
                        SET status = 'running',
                            warning = NULL,
                            error_message = NULL,
                            updated_at = ?
                        WHERE id = ?
                          AND status = 'queued'
                        """,
                        [now, task_id],
                    )
                    cur = conn.execute(
                        """
                        SELECT *
                        FROM task_runs
                        WHERE id = ?
                          AND status = 'running'
                          AND updated_at = ?
                        """,
                        [task_id, now],
                    )
                    claimed_columns = [desc[0] for desc in cur.description]
                    row = cur.fetchone()
                    conn.execute("COMMIT")
                    return dict(zip(claimed_columns, row)) if row else None
                except Exception:
                    conn.execute("ROLLBACK")
                    raise

    def _dispatch_queued_task(self, task: Dict[str, Any], payload: Dict[str, Any]) -> None:
        kind = task.get("kind")
        task_id = task["id"]
        if kind == "update":
            self._run_update(task_id, payload)
            return
        if kind == "analyze":
            if self.analysis_runner is None:
                raise RuntimeError("分析服务尚未就绪。")
            self._run_analysis(task_id, payload.get("config") or {}, self.analysis_runner, run_id=payload.get("run_id"))
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
        source = BaostockSource()
        result = self.baostock_guard.call(
            "Baostock", "股票基础信息",
            lambda: source.fetch_stock_basics(include_bj=settings.include_bj, exclude_star=settings.exclude_star_board),
            ignore_circuit=True,
        )
        return [{"source": "Baostock", "rows": len(result.frame), "status": result.status}]

    def _run_analysis(
        self,
        task_id: str,
        config: Dict[str, Any],
        analysis_runner: Any,
        run_id: Optional[str] = None,
    ) -> None:
        try:
            def progress(stage: str, processed: int, total: int) -> None:
                self._patch_task(
                    task_id,
                    stage=stage,
                    source="本地仓库",
                    processed=processed,
                    total=total,
                )

            run_id = analysis_runner.run(config, progress=progress, run_id=run_id, task_id=task_id)
            candidates = self.data_service.candidates(run_id, limit=1)
            candidate_count = int(
                self.db.scalar("SELECT COUNT(*) FROM candidate_results WHERE run_id = ?", [run_id])
                or 0
            )
            self._patch_task(
                task_id,
                status="completed_full",
                stage="分析完成",
                processed=7,
                total=7,
                success=1,
                summary={
                    "analysis_run_id": run_id,
                    "candidate_count": candidate_count,
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
        force = bool(options.get("force"))
        incremental = options.get("mode", "daily_light") == "daily_light" and not force
        warnings: List[str] = []
        source = BaostockSource()
        context = source.session() if callable(getattr(source, "session", None)) else nullcontext(None)
        try:
            with context as client:
                target = self._target_history_date()
                self._refresh_trade_calendar(target - timedelta(days=35), target + timedelta(days=35), source=source, client=client)
                target = self._latest_cached_trading_day(target) or target
                self._patch_task(task_id, stage="刷新股票池", source="Baostock")
                stock_count = self._update_basics(
                    force, settings.include_bj, settings.exclude_star_board, warnings,
                    source=source, client=client,
                )
                if not stock_count:
                    raise SourceUnavailable("股票池为空，请检查 Baostock 连接后重试。")
                self.record_checkpoint(task_id, "stock_basic", "股票基础信息", target, "all", "completed", rows_written=stock_count)
                self._update_baostock_industry(force=force, warnings=warnings, source=source, client=client)
                stocks = self._history_stocks_for_update(
                    limit=int(options.get("limit") or settings.update_limit or 0),
                    light=incremental, target_history_date=target,
                )
                self._patch_task(task_id, stage="补齐收盘日线", source="Baostock", total=len(stocks))
                self.record_checkpoint(task_id, "history_qfq", "收盘日线", target, "all", "running")
                success, failed, skipped = self._update_history(
                    stocks, target - timedelta(days=settings.default_history_days), target,
                    force, task_id, incremental=incremental, target_history_date=target,
                    source=source, client=client,
                )
                coverage = self.db.scalar(
                    "SELECT COUNT(*) FROM historical_bars h JOIN stock_basic b USING (code) "
                    "WHERE h.date = ? AND b.suspended IS DISTINCT FROM TRUE", [target],
                ) or 0
                active_count = self.data_service.active_stock_count()
                if active_count and coverage / active_count < 0.95:
                    warnings.append(f"{target} 日线覆盖 {coverage}/{active_count}，未完整覆盖股票池。")
                self.record_checkpoint(task_id, "history_qfq", "收盘日线", target, "all", "partial" if failed or warnings else "completed", rows_written=success)
                self._patch_task(task_id, stage="估算流通市值", source="本地日线")
                float_count = self._update_float_values_from_history(target)
                self._patch_task(
                    task_id, status="completed_partial" if failed or warnings else "completed_full",
                    stage="部分完成" if failed or warnings else "日线更新完成",
                    success=success, failed=failed, skipped=skipped,
                    warning="；".join(warnings) or None,
                    summary={"mode": "daily_light" if incremental else "full", "target_history_date": target.isoformat(),
                             "stock_count": stock_count, "covered_count": coverage, "history_success": success,
                             "history_failed": failed, "history_skipped": skipped,
                             "float_market_value_count": float_count, "warnings": warnings},
                    finished_at=datetime.utcnow(),
                )
        except Exception as exc:
            self._patch_task(task_id, status="failed", stage="日线更新失败", error_message=str(exc), warning=str(exc), finished_at=datetime.utcnow())

    def _update_float_values_from_history(self, target: date) -> int:
        rows = self.db.query(
            """SELECT code, date, volume / (turn / 100) AS float_shares,
                      volume / (turn / 100) * close AS float_market_value,
                      '本地历史换手率估算' AS source, current_timestamp AS updated_at
               FROM historical_bars
               WHERE date = ? AND volume > 0 AND turn > 0 AND close > 0""", [target],
        )
        return self.db.upsert("float_market_values", rows, ["code", "date"])


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

    def _update_basics(
        self,
        force: bool,
        include_bj: bool,
        exclude_star: bool,
        warnings: List[str],
        source: Optional[BaostockSource] = None,
        client: Any = None,
    ) -> int:
        existing = self.db.scalar("SELECT COUNT(*) FROM stock_basic") or 0
        rows_written = 0
        last_refresh = self.db.scalar("SELECT MAX(updated_at) FROM stock_basic")
        fresh = last_refresh is not None and datetime.utcnow() - last_refresh < timedelta(days=7)
        if existing and fresh and not force:
            self.public_guard.record(
                "本地缓存",
                "股票基础信息",
                "available",
                payload={"rows": existing, "cache": True},
            )
            return int(existing)
        baostock = source or BaostockSource()
        try:
            if client is None:
                frame = baostock.fetch_stock_basics(include_bj=include_bj, exclude_star=exclude_star)
            else:
                frame = baostock.fetch_stock_basics(
                    include_bj=include_bj,
                    exclude_star=exclude_star,
                    client=client,
                )
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


    def _update_baostock_industry(
        self,
        force: bool,
        warnings: List[str],
        source: Optional[BaostockSource] = None,
        client: Any = None,
    ) -> int:
        latest = _datetime_option(self.db.scalar("SELECT MAX(updated_at) FROM stock_industry"))
        refresh_after = timedelta(days=getattr(settings, "baostock_industry_refresh_days", 30))
        if not force and latest and datetime.utcnow() - latest < refresh_after:
            return int(self.db.scalar("SELECT COUNT(*) FROM stock_industry") or 0)
        try:
            resolved_source = source or BaostockSource()
            frame = (
                resolved_source.fetch_stock_industry(client=client)
                if client is not None
                else resolved_source.fetch_stock_industry()
            )
            if frame is None or frame.empty:
                raise SourceUnavailable("Baostock 行业分类为空。")
            count = self.db.upsert("stock_industry", frame.to_dict("records"), ["code"])
            self.baostock_guard.record(
                "Baostock",
                "概念/行业成分",
                "available",
                payload={"rows": count, "kind": "industry"},
            )
            return count
        except Exception as exc:
            warnings.append(f"Baostock 行业分类沿用本地缓存：{exc}")
            self.baostock_guard.record(
                "Baostock",
                "概念/行业成分",
                "failed",
                message=str(exc),
                ttl_minutes=60,
            )
            return int(self.db.scalar("SELECT COUNT(*) FROM stock_industry") or 0)

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


    def _update_history(
        self,
        stocks: List[Dict[str, Any]],
        start: date,
        end: date,
        force: bool,
        task_id: str,
        incremental: bool = False,
        target_history_date: Optional[date] = None,
        source: Optional[BaostockSource] = None,
        client: Any = None,
    ) -> tuple:
        baostock = source or BaostockSource()
        success = 0
        failed = 0
        skipped = 0
        consecutive_failures = 0
        max_consecutive_failures = max(1, int(settings.baostock_max_consecutive_failures))
        total = len(stocks)
        target = target_history_date or self._target_history_date()
        session_context = (
            nullcontext(client)
            if client is not None
            else baostock.session() if callable(getattr(baostock, "session", None)) else nullcontext(None)
        )
        with session_context as session_client:
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
                fetch_start = self._history_fetch_start(start, latest, incremental)
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
                    if session_client is None:
                        frame = baostock.fetch_history(code, fetch_start, end)
                    else:
                        frame = baostock.fetch_history(code, fetch_start, end, client=session_client)
                    if frame.empty:
                        raise RuntimeError("Baostock 历史行情为空")
                    self.db.upsert("historical_bars", frame.to_dict("records"), ["code", "date"])
                    success += 1
                    consecutive_failures = 0
                except Exception as exc:
                    failed += 1
                    consecutive_failures += 1
                    self.baostock_guard.record(
                        "Baostock",
                        "历史 K 线",
                        "failed",
                        message=f"{code}: {exc}",
                        ttl_minutes=15,
                    )
                    if consecutive_failures >= max_consecutive_failures:
                        self._patch_task(
                            task_id,
                            current_stock=code,
                            total=total,
                            processed=index,
                            success=success,
                            failed=failed,
                            skipped=skipped,
                        )
                        raise SourceUnavailable(
                            f"Baostock 连续 {consecutive_failures} 只股票请求失败，"
                            "已中止本轮历史更新，避免阻塞任务队列。"
                        ) from exc
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


    @staticmethod
    def _target_history_date(now: Optional[datetime] = None) -> date:
        current = now or datetime.now(CHINA_TZ)
        if current.tzinfo is not None:
            current = current.astimezone(CHINA_TZ).replace(tzinfo=None)
        current_day = current.date()
        if current.weekday() < 5 and current.hour >= HISTORY_CLOSE_HOUR:
            return current_day
        return UpdateService._previous_weekday(current_day)

    def is_trading_day(self, day: date) -> bool:
        cached = self.db.scalar("SELECT is_trading_day FROM trading_calendar WHERE date = ?", [day])
        if cached is None:
            return day.weekday() < 5
        return bool(cached)

    def _latest_cached_trading_day(self, day: date) -> Optional[date]:
        value = self.db.scalar(
            "SELECT MAX(date) FROM trading_calendar WHERE date <= ? AND is_trading_day IS TRUE",
            [day],
        )
        return _date_option(value)

    def _refresh_trade_calendar(
        self,
        start: date,
        end: date,
        source: Optional[BaostockSource] = None,
        client: Any = None,
    ) -> int:
        try:
            resolved_source = source or BaostockSource()
            frame = (
                resolved_source.fetch_trade_calendar(start, end, client=client)
                if client is not None
                else resolved_source.fetch_trade_calendar(start, end)
            )
            if frame is None or frame.empty:
                return 0
            count = self.db.upsert("trading_calendar", frame.to_dict("records"), ["date"])
            self.baostock_guard.record(
                "Baostock",
                "交易日历",
                "available",
                payload={"rows": count, "start": start.isoformat(), "end": end.isoformat()},
            )
            return count
        except Exception as exc:
            self.baostock_guard.record(
                "Baostock",
                "交易日历",
                "failed",
                message=str(exc),
                ttl_minutes=60,
            )
            return 0

    @staticmethod
    def _previous_weekday(day: date) -> date:
        target = day - timedelta(days=1)
        while target.weekday() >= 5:
            target -= timedelta(days=1)
        return target

    @staticmethod
    def _history_fetch_start(default_start: date, latest: Any, incremental: bool) -> date:
        # Forward-adjusted prices can rebase after corporate actions. Refresh the
        # analysis window together so new bars never join an older price basis.
        return default_start

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
            "payload_hash": values.get("payload_hash") or _task_payload_hash(values.get("payload") or {}),
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


def _date_option(value: Any) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _datetime_option(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None
