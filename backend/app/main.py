from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router, update_service
from backend.app.config import settings
from backend.app.services.daily_brief_scheduler import DailyBriefScheduler
from backend.app.services.intraday_schedule import parse_intraday_schedule
from backend.app.services.intraday_scheduler import IntradayScheduler


app = FastAPI(title="A-Share Signal", version="1.0.0")
app.include_router(router)
intraday_scheduler = IntradayScheduler(
    update_service,
    poll_seconds=settings.intraday_scheduler_poll_seconds,
    catchup_minutes=settings.intraday_scheduler_catchup_minutes,
    slots=parse_intraday_schedule(settings.intraday_schedule),
)
daily_brief_scheduler = DailyBriefScheduler(
    update_service,
    poll_seconds=settings.daily_brief_scheduler_poll_seconds,
    schedule_time=settings.daily_brief_schedule_time,
)


@app.on_event("startup")
def start_schedulers() -> None:
    update_service.ensure_daily_brief()
    if settings.intraday_scheduler_enabled:
        intraday_scheduler.start()
    if settings.daily_brief_scheduler_enabled:
        daily_brief_scheduler.start()


@app.on_event("shutdown")
def stop_schedulers() -> None:
    intraday_scheduler.stop()
    daily_brief_scheduler.stop()


@app.get("/")
def root() -> FileResponse:
    index = settings.frontend_dist / "index.html"
    if index.exists():
        return FileResponse(index)
    return FileResponse(Path(__file__).resolve().parents[2] / "frontend" / "public" / "fallback.html")


if settings.frontend_dist.exists():
    assets = settings.frontend_dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")


@app.get("/{path:path}")
def spa_fallback(path: str) -> FileResponse:
    index = settings.frontend_dist / "index.html"
    if index.exists():
        return FileResponse(index)
    return FileResponse(Path(__file__).resolve().parents[2] / "frontend" / "public" / "fallback.html")
