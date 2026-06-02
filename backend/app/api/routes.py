from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from backend.app.db import get_database
from backend.app.schema import migrate
from backend.app.config import settings
from backend.app.services.analysis_service import AnalysisService
from backend.app.services.backtest_service import BacktestService
from backend.app.services.candidate_summary_service import CandidateSummaryService
from backend.app.services.data_service import DataService
from backend.app.services.intraday_service import IntradayRadarService
from backend.app.services.indicator_registry import indicator_library
from backend.app.services.strategy_service import StrategyService
from backend.app.services.update_service import TaskBusy, UpdateService
from backend.app.services.watchlist_service import WatchlistService


router = APIRouter(prefix="/api")

db = get_database()
migrate(db)
data_service = DataService(db)
strategy_service = StrategyService(db)
analysis_service = AnalysisService(db)
update_service = UpdateService(db)
backtest_service = BacktestService(db, analysis_service)
intraday_service = IntradayRadarService(db)
watchlist_service = WatchlistService(db)
candidate_summary_service = CandidateSummaryService(db)
update_service.configure_runners(analysis_service, backtest_service, candidate_summary_service)
update_service.recover_interrupted_tasks()
update_service.kick_queue()


@router.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "database": str(db.path),
        "schema_version": db.scalar("SELECT MAX(version) FROM schema_migrations"),
        "source_diagnostics": data_service.source_diagnostics(),
    }


@router.get("/bootstrap")
def bootstrap() -> Dict[str, Any]:
    update_service.ensure_daily_brief()
    return {
        "overview": data_service.overview(),
        "capabilities": data_service.capabilities(),
        "indicator_library": indicator_library(),
        "strategies": strategy_service.list_presets(),
        "default_strategy": strategy_service.default_config(),
        "update_status": data_service.latest_task("update"),
        "analyze_status": data_service.latest_task("analyze"),
        "backtest_status": data_service.latest_task("backtest"),
        "intraday_status": data_service.latest_task("intraday"),
        "brief_status": data_service.latest_task("brief"),
        "latest_analysis": data_service.latest_analysis_run(),
        "latest_backtest": data_service.latest_backtest_run(),
        "daily_brief": data_service.latest_daily_brief(),
        "intraday": intraday_service.latest(limit=200),
        "candidates": data_service.candidates(limit=50),
        "backtest": data_service.backtest_result(limit=200),
        "watchlist": watchlist_service.result(),
        "runtime_health": data_service.runtime_health(
            scheduler_enabled=settings.intraday_scheduler_enabled,
            poll_seconds=settings.intraday_scheduler_poll_seconds,
            catchup_minutes=settings.intraday_scheduler_catchup_minutes,
            schedule=settings.intraday_schedule,
        ),
    }


@router.get("/data/overview")
def data_overview() -> Dict[str, Any]:
    return data_service.overview()


@router.get("/data/capabilities")
def data_capabilities() -> Dict[str, Any]:
    return {"rows": data_service.capabilities()}


@router.get("/data/source-diagnostics")
def data_source_diagnostics() -> Dict[str, Any]:
    return data_service.source_diagnostics()


@router.get("/market/overview")
def market_overview() -> Dict[str, Any]:
    return data_service.market_overview()


@router.get("/market/sector-heatmap")
def market_sector_heatmap(
    type: str = Query(default="concept"),
    metric: str = Query(default="heat"),
) -> Dict[str, Any]:
    return {"rows": data_service.sector_heatmap(type, metric=metric)}


@router.get("/indicators")
def indicators() -> Dict[str, Any]:
    return indicator_library()


@router.get("/signal-modes")
def signal_modes() -> Dict[str, Any]:
    raise HTTPException(status_code=410, detail="信号模式已废弃；请使用特征驱动策略参数。")


@router.post("/signal-modes")
def save_signal_mode(payload: Dict[str, Any]) -> Dict[str, Any]:
    raise HTTPException(status_code=410, detail="信号模式已废弃；请使用特征驱动策略参数。")


@router.post("/signal-modes/new")
def create_signal_mode(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    raise HTTPException(status_code=410, detail="信号模式已废弃；请使用特征驱动策略参数。")


@router.post("/signal-modes/{mode_id}/duplicate")
def duplicate_signal_mode(mode_id: str) -> Dict[str, Any]:
    raise HTTPException(status_code=410, detail="信号模式已废弃；请使用特征驱动策略参数。")


@router.delete("/signal-modes/{mode_id}")
def delete_signal_mode(mode_id: str) -> Dict[str, Any]:
    raise HTTPException(status_code=410, detail="信号模式已废弃；请使用特征驱动策略参数。")


@router.post("/data/probe")
def probe_data_sources(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"rows": update_service.probe_sources(payload or {})}


@router.get("/data/stocks")
def data_stocks(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: str = "",
    exchange: str = "",
    board: str = "",
    status: str = "active",
) -> Dict[str, Any]:
    return data_service.list_stocks(limit=limit, offset=offset, search=search, exchange=exchange, board=board, status=status)


@router.get("/data/stocks/{code}")
def data_stock_detail(code: str) -> Dict[str, Any]:
    detail = data_service.stock_detail(code)
    if not detail.get("basic"):
        raise HTTPException(status_code=404, detail="股票不存在。")
    return detail


@router.post("/tasks/update")
def start_update(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        task_id = update_service.start_update(payload or {})
    except TaskBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"task_id": task_id, "status": "queued"}


@router.post("/tasks/sync-today")
def sync_today(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = dict(payload or {})
    body["mode"] = "daily_light"
    try:
        task_id = update_service.start_update(body)
    except TaskBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"task_id": task_id, "status": "queued"}


@router.get("/tasks")
def list_tasks(
    status: str = Query(default="queued,running"),
    limit: int = Query(default=50, ge=1, le=200),
) -> Dict[str, Any]:
    statuses = [item.strip() for item in status.split(",") if item.strip()]
    return {"rows": data_service.task_runs(statuses=statuses, limit=limit)}


@router.get("/tasks/{task_id}/dag")
def task_dag(task_id: str) -> Dict[str, Any]:
    return data_service.task_dag(task_id)


@router.get("/tasks/{task_id}/checkpoints")
def task_checkpoints(task_id: str) -> Dict[str, Any]:
    return {"rows": data_service.task_checkpoints(task_id)}


@router.get("/status/update")
def update_status() -> Dict[str, Any]:
    return {"task": data_service.latest_task("update")}


@router.post("/tasks/intraday-snapshot")
def start_intraday_snapshot(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        task_id = update_service.start_intraday_sample(payload or {})
    except TaskBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"task_id": task_id, "status": "queued"}


@router.get("/status/intraday")
def intraday_status() -> Dict[str, Any]:
    return {"task": data_service.latest_task("intraday"), "intraday": intraday_service.latest(limit=200)}


@router.get("/intraday")
def intraday_latest(
    limit: int = Query(default=200, ge=1, le=500),
) -> Dict[str, Any]:
    return intraday_service.latest(limit=limit)


@router.get("/intraday/boards")
def intraday_boards(
    limit: int = Query(default=80, ge=1, le=300),
) -> Dict[str, Any]:
    return intraday_service.boards(limit=limit)


@router.get("/intraday/timeline/{code}")
def intraday_timeline(
    code: str,
    trade_date: Optional[str] = None,
    limit: int = Query(default=80, ge=1, le=200),
) -> Dict[str, Any]:
    return intraday_service.timeline(code=code, trade_date=trade_date, limit=limit)


@router.get("/runtime/health")
def runtime_health() -> Dict[str, Any]:
    return data_service.runtime_health(
        scheduler_enabled=settings.intraday_scheduler_enabled,
        poll_seconds=settings.intraday_scheduler_poll_seconds,
        catchup_minutes=settings.intraday_scheduler_catchup_minutes,
        schedule=settings.intraday_schedule,
    )


@router.get("/daily-brief")
def daily_brief() -> Dict[str, Any]:
    update_service.ensure_daily_brief()
    return {"brief": data_service.latest_daily_brief(), "task": data_service.latest_task("brief")}


@router.post("/daily-brief/regenerate")
def regenerate_daily_brief(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    task_id = update_service.start_daily_brief({**(payload or {}), "reason": "manual"})
    return {"task_id": task_id, "status": "queued"}


@router.get("/watchlist")
def watchlist() -> Dict[str, Any]:
    return watchlist_service.result()


@router.post("/watchlist/items")
def add_watchlist_items(payload: Dict[str, Any]) -> Dict[str, Any]:
    return watchlist_service.add_items(payload)


@router.delete("/watchlist/batches/{batch_id}")
def delete_watchlist_batch(batch_id: str) -> Dict[str, Any]:
    watchlist_service.delete_batch(batch_id)
    return {"ok": True}


@router.patch("/watchlist/batches/{batch_id}")
def update_watchlist_batch(batch_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    result = watchlist_service.update_batch(batch_id, payload)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail="观察批次不存在。")
    return result


@router.delete("/watchlist/batches/{batch_id}/items/{code}")
def delete_watchlist_item(batch_id: str, code: str) -> Dict[str, Any]:
    watchlist_service.delete_item(batch_id, code)
    return {"ok": True}


@router.patch("/watchlist/batches/{batch_id}/items/{code}")
def update_watchlist_item(batch_id: str, code: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    result = watchlist_service.update_item(batch_id, code, payload)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail="观察记录不存在。")
    return result


@router.get("/intraday/config")
def intraday_config() -> Dict[str, Any]:
    return {"config": intraday_service.get_config()}


@router.put("/intraday/config")
def save_intraday_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"config": intraday_service.save_config(payload.get("config") or payload)}


@router.post("/tasks/analyze")
def start_analyze(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = payload or {}
    config = body.get("config")
    preset_id = body.get("preset_id")
    strategy_name = body.get("strategy_name") or body.get("name") or body.get("preset_name")
    if preset_id and not config:
        preset = strategy_service.get_preset(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail="策略预设不存在。")
        config = preset["config"]
        strategy_name = strategy_name or preset.get("name")
    config = dict(config or strategy_service.default_config())
    if not strategy_name:
        strategy_name = config.get("strategy_name") or config.get("name") or config.get("preset_name")
    if strategy_name:
        name = str(strategy_name).strip()
        config["strategy_name"] = name
        config["name"] = name
        config["preset_name"] = name
    try:
        task_id, run_id = update_service.start_analysis(config, analysis_service)
    except TaskBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"task_id": task_id, "run_id": run_id, "status": "queued"}


@router.get("/status/analyze")
def analyze_status() -> Dict[str, Any]:
    return {
        "task": data_service.latest_task("analyze"),
        "analysis": data_service.latest_analysis_run(),
    }


@router.post("/tasks/backtest")
def start_backtest(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = payload or {}
    config = body.get("config") or strategy_service.default_config()
    body["config"] = config
    try:
        task_id, run_id = update_service.start_backtest(body, backtest_service)
    except TaskBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"task_id": task_id, "run_id": run_id, "status": "queued"}


@router.get("/status/backtest")
def backtest_status() -> Dict[str, Any]:
    return {
        "task": data_service.latest_task("backtest"),
        "backtest": data_service.latest_backtest_run(),
    }


@router.get("/candidates")
def candidates(
    run_id: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> Dict[str, Any]:
    return data_service.candidates(run_id=run_id, limit=limit)


@router.get("/runs")
def runs() -> Dict[str, Any]:
    return {"rows": data_service.analysis_runs()}


@router.get("/analysis/reports")
def analysis_reports() -> Dict[str, Any]:
    return data_service.analysis_reports(per_mode_limit=3)


@router.get("/analysis/reports/{run_id}")
def analysis_report(
    run_id: str,
    limit: int = Query(default=100, ge=1, le=500),
) -> Dict[str, Any]:
    report = data_service.analysis_report(run_id=run_id, limit=limit)
    if not report.get("analysis"):
        raise HTTPException(status_code=404, detail="分析报告不存在。")
    return report


@router.get("/analysis/candidates/{run_id}/{code}/ai-summary")
def get_candidate_ai_summary(run_id: str, code: str) -> Dict[str, Any]:
    return data_service.candidate_ai_summary(run_id=run_id, code=code)


@router.post("/analysis/candidates/{run_id}/{code}/ai-summary")
def candidate_ai_summary(run_id: str, code: str, payload: Optional[Dict[str, Any]] = None) -> JSONResponse:
    return JSONResponse(status_code=410, content={"detail": "请使用 POST /api/tasks/candidate-ai-summary 启动候选解释任务。"})


@router.post("/tasks/candidate-ai-summary")
def start_candidate_ai_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        task_id, identity = update_service.start_candidate_ai_summary(payload, candidate_summary_service)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "task_id": task_id,
        "run_id": identity["run_id"],
        "code": identity["code"],
        "input_hash": identity["input_hash"],
        "status": identity.get("status") or "queued",
    }


@router.get("/backtests")
def backtest_runs() -> Dict[str, Any]:
    return {"rows": data_service.backtest_runs()}


@router.get("/backtests/latest")
def latest_backtest(
    limit: int = Query(default=500, ge=1, le=2000),
) -> Dict[str, Any]:
    return data_service.backtest_result(limit=limit)


@router.get("/backtests/{run_id}")
def backtest_result(
    run_id: str,
    limit: int = Query(default=500, ge=1, le=2000),
) -> Dict[str, Any]:
    result = data_service.backtest_result(run_id=run_id, limit=limit)
    if not result.get("run"):
        raise HTTPException(status_code=404, detail="回测报告不存在。")
    return result


@router.post("/backtest/signal-evaluation")
def run_signal_evaluation(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = payload or {}
    body["config"] = body.get("config") or strategy_service.default_config()
    try:
        task_id, run_id = update_service.start_signal_evaluation(body, backtest_service)
    except TaskBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"task_id": task_id, "run_id": run_id, "status": "queued"}


@router.get("/backtest/signal-evaluation/{run_id}")
def signal_evaluation_result(
    run_id: str,
    limit: int = Query(default=500, ge=1, le=5000),
) -> Dict[str, Any]:
    result = data_service.backtest_result(run_id=run_id, limit=limit)
    if not result.get("run"):
        raise HTTPException(status_code=404, detail="信号评估报告不存在。")
    return result


@router.post("/backtest/portfolio")
def run_portfolio_backtest(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = payload or {}
    body["config"] = body.get("config") or strategy_service.default_config()
    try:
        task_id, run_id = update_service.start_portfolio_backtest(body, backtest_service)
    except TaskBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"task_id": task_id, "run_id": run_id, "status": "queued"}


@router.get("/backtest/portfolio/{run_id}")
def portfolio_backtest_result(run_id: str) -> Dict[str, Any]:
    result = backtest_service.portfolio_result(run_id)
    if not result.get("run"):
        raise HTTPException(status_code=404, detail="组合回测报告不存在。")
    return result


@router.get("/strategies")
def list_strategies() -> Dict[str, Any]:
    return {
        "rows": strategy_service.list_presets(),
        "default_config": strategy_service.default_config(),
    }


@router.get("/strategies/{preset_id}/versions")
def strategy_versions(preset_id: str) -> Dict[str, Any]:
    preset = strategy_service.get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="策略预设不存在。")
    return {"rows": strategy_service.list_versions(preset_id)}


@router.post("/strategies")
def save_strategy(payload: Dict[str, Any]) -> Dict[str, Any]:
    preset = strategy_service.save_preset(
        name=payload.get("name") or "未命名策略",
        config=payload.get("config") or {},
        preset_id=payload.get("id"),
        set_default=bool(payload.get("set_default")),
    )
    return {"preset": preset}


@router.post("/strategies/{preset_id}/duplicate")
def duplicate_strategy(preset_id: str) -> Dict[str, Any]:
    preset = strategy_service.get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="策略预设不存在。")
    duplicate = strategy_service.save_preset(
        name=f"{preset['name']} 副本",
        config=preset["config"],
    )
    return {"preset": duplicate}


@router.delete("/strategies/{preset_id}")
def delete_strategy(preset_id: str) -> Dict[str, Any]:
    if not strategy_service.delete_preset(preset_id):
        raise HTTPException(status_code=400, detail="策略不存在或已经删除。")
    return {"ok": True}


@router.post("/strategies/{preset_id}/default")
def set_default_strategy(preset_id: str) -> Dict[str, Any]:
    if not strategy_service.set_default(preset_id):
        raise HTTPException(status_code=404, detail="策略预设不存在。")
    return {"ok": True}


@router.post("/strategies/system/reset")
def reset_system_strategies() -> Dict[str, Any]:
    return {"rows": strategy_service.restore_system_defaults()}
