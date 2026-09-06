from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.app.db import get_database
from backend.app.config import settings
from backend.app.services.analysis_service import AnalysisService
from backend.app.services.data_service import DataService
from backend.app.services.indicator_registry import indicator_library
from backend.app.services.strategy_service import StrategyService
from backend.app.services.update_service import TaskBusy, UpdateService
from backend.app.services.watchlist_service import WatchlistService


router = APIRouter(prefix="/api")

db = get_database()
data_service = DataService(db)
strategy_service = StrategyService(db)
analysis_service = AnalysisService(db)
update_service = UpdateService(db)
watchlist_service = WatchlistService(db)
update_service.configure_runners(analysis_runner=analysis_service, strategy_service=strategy_service)


def _runtime_health_payload() -> Dict[str, Any]:
    return {
        "daily_update_scheduler": {
            "enabled": settings.daily_update_scheduler_enabled,
            "schedule": settings.daily_update_schedule_time,
            "timezone": "Asia/Shanghai",
        },
        "database": {"memory_limit": settings.db_memory_limit, "threads": settings.db_threads},
    }


@router.get("/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "database": str(db.path),
        "schema_version": db.scalar("SELECT MAX(version) FROM schema_migrations"),
    }


@router.get("/bootstrap")
def bootstrap() -> Dict[str, Any]:
    return {
        "indicator_library": indicator_library(),
        "strategies": strategy_service.list_presets(),
        "default_strategy": strategy_service.default_config(),
    }


@router.get("/review/overview")
def review_overview() -> Dict[str, Any]:
    return data_service.review_overview()


@router.get("/data/overview")
def data_overview() -> Dict[str, Any]:
    return data_service.review_overview()




@router.get("/data/source-diagnostics")
def data_source_diagnostics() -> Dict[str, Any]:
    return data_service.source_diagnostics()


@router.get("/indicators")
def indicators() -> Dict[str, Any]:
    return indicator_library()








@router.post("/tasks/update")
def start_update(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = payload or {}
    if body.get("mode", "daily_light") not in {"daily_light", "full"}:
        raise HTTPException(status_code=400, detail="仅支持收盘日线更新。")
    body.setdefault("mode", "daily_light")
    try:
        task_id = update_service.start_update(body)
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




@router.get("/tasks/{task_id}/checkpoints")
def task_checkpoints(task_id: str) -> Dict[str, Any]:
    return {"rows": data_service.task_checkpoints(task_id)}


@router.get("/status/update")
def update_status() -> Dict[str, Any]:
    return {"task": data_service.latest_task("update")}


@router.get("/runtime/health")
def runtime_health() -> Dict[str, Any]:
    return _runtime_health_payload()


@router.get("/watchlist")
def watchlist() -> Dict[str, Any]:
    return watchlist_service.result()


@router.get("/watchlist/codes")
def watchlist_codes() -> Dict[str, Any]:
    return {"codes": [row["code"] for row in db.query("SELECT DISTINCT code FROM watchlist_items")]}


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
    return data_service.analysis_reports()


@router.get("/analysis/reports/{run_id}")
def analysis_report(
    run_id: str,
    limit: int = Query(default=100, ge=1, le=500),
) -> Dict[str, Any]:
    report = data_service.analysis_report(run_id=run_id, limit=limit)
    if not report.get("analysis"):
        raise HTTPException(status_code=404, detail="分析报告不存在。")
    return report


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
