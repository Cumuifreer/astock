from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.app.auth import basic_auth_matches
from backend.app.api.routes import router, update_service, db
from backend.app.schema import migrate
from backend.app.config import settings
from backend.app.services.daily_update_scheduler import DailyUpdateScheduler


app = FastAPI(title="A-Share Signal", version="1.0.0")


@app.middleware("http")
async def optional_http_basic_auth(request: Request, call_next):
    username = settings.http_basic_username
    password = settings.http_basic_password
    if username and password:
        authorization = request.headers.get("Authorization", "")
        if not basic_auth_matches(authorization, username, password):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="A-Share Signal", charset="UTF-8"'},
            )
    return await call_next(request)


app.include_router(router)
daily_update_scheduler = DailyUpdateScheduler(
    update_service,
    poll_seconds=settings.daily_update_scheduler_poll_seconds,
    schedule_time=settings.daily_update_schedule_time,
    mode=settings.daily_update_mode,
)


@app.on_event("startup")
def start_schedulers() -> None:
    migrate(db)
    update_service.recover_interrupted_tasks()
    update_service.db.execute(
        "UPDATE task_runs SET status = 'failed', finished_at = current_timestamp, "
        "error_message = '该功能已停用' WHERE status = 'queued' AND kind NOT IN ('update', 'analyze')",
        write=True,
    )
    update_service.kick_queue()
    if getattr(settings, "daily_update_scheduler_enabled", False):
        daily_update_scheduler.start()


@app.on_event("shutdown")
def stop_schedulers() -> None:
    daily_update_scheduler.stop()
    update_service.close()


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
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="接口不存在或已停用。")
    index = settings.frontend_dist / "index.html"
    if index.exists():
        return FileResponse(index)
    return FileResponse(Path(__file__).resolve().parents[2] / "frontend" / "public" / "fallback.html")
