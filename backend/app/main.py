from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router, update_service
from backend.app.config import settings
from backend.app.services.intraday_scheduler import IntradayScheduler


app = FastAPI(title="A-Share Signal", version="1.0.0")
app.include_router(router)
intraday_scheduler = IntradayScheduler(
    update_service,
    poll_seconds=settings.intraday_scheduler_poll_seconds,
    catchup_minutes=settings.intraday_scheduler_catchup_minutes,
)


@app.on_event("startup")
def start_intraday_scheduler() -> None:
    if settings.intraday_scheduler_enabled:
        intraday_scheduler.start()


@app.on_event("shutdown")
def stop_intraday_scheduler() -> None:
    intraday_scheduler.stop()


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
