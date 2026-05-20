from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.config import settings


app = FastAPI(title="A-Share Signal", version="1.0.0")
app.include_router(router)


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
