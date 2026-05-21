from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.app.db import get_database
from backend.app.schema import migrate
from backend.app.services.analysis_service import AnalysisService
from backend.app.services.data_service import DataService
from backend.app.services.strategy_service import StrategyService
from backend.app.services.update_service import TaskBusy, UpdateService


router = APIRouter(prefix="/api")

db = get_database()
migrate(db)
data_service = DataService(db)
strategy_service = StrategyService(db)
analysis_service = AnalysisService(db)
update_service = UpdateService(db)


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
        "overview": data_service.overview(),
        "capabilities": data_service.capabilities(),
        "strategies": strategy_service.list_presets(),
        "default_strategy": strategy_service.default_config(),
        "update_status": data_service.latest_task("update"),
        "analyze_status": data_service.latest_task("analyze"),
        "latest_analysis": data_service.latest_analysis_run(),
        "candidates": data_service.candidates(limit=50),
    }


@router.get("/data/overview")
def data_overview() -> Dict[str, Any]:
    return data_service.overview()


@router.get("/data/capabilities")
def data_capabilities() -> Dict[str, Any]:
    return {"rows": data_service.capabilities()}


@router.post("/data/probe")
def probe_data_sources(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"rows": update_service.probe_sources(payload or {})}


@router.get("/data/stocks")
def data_stocks(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    search: str = "",
) -> Dict[str, Any]:
    return data_service.list_stocks(limit=limit, offset=offset, search=search)


@router.post("/tasks/update")
def start_update(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    try:
        task_id = update_service.start_update(payload or {})
    except TaskBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"task_id": task_id, "status": "running"}


@router.get("/status/update")
def update_status() -> Dict[str, Any]:
    return {"task": data_service.latest_task("update")}


@router.post("/tasks/analyze")
def start_analyze(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = payload or {}
    config = body.get("config")
    preset_id = body.get("preset_id")
    if preset_id and not config:
        preset = strategy_service.get_preset(preset_id)
        if not preset:
            raise HTTPException(status_code=404, detail="策略预设不存在。")
        config = preset["config"]
    config = config or strategy_service.default_config()
    try:
        task_id = update_service.start_analysis(config, analysis_service)
    except TaskBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"task_id": task_id, "status": "running"}


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


@router.get("/strategies")
def list_strategies() -> Dict[str, Any]:
    return {
        "rows": strategy_service.list_presets(),
        "default_config": strategy_service.default_config(),
    }


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
        raise HTTPException(status_code=400, detail="系统预设不能删除，或预设不存在。")
    return {"ok": True}


@router.post("/strategies/{preset_id}/default")
def set_default_strategy(preset_id: str) -> Dict[str, Any]:
    if not strategy_service.set_default(preset_id):
        raise HTTPException(status_code=404, detail="策略预设不存在。")
    return {"ok": True}


@router.post("/strategies/system/reset")
def reset_system_strategies() -> Dict[str, Any]:
    return {"rows": strategy_service.restore_system_defaults()}
