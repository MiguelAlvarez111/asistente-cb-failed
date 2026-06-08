from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes_auth import router as auth_router
from backend.app.api.routes_export import router as export_router
from backend.app.api.routes_health import router as health_router
from backend.app.api.routes_jobs import router as jobs_router
from backend.app.api.routes_results import router as results_router
from backend.app.api.routes_uploads import router as uploads_router
from backend.app.core.config import get_settings
from backend.app.core.logging import configure_logging
from backend.app.repositories.job_repository import job_repository

configure_logging()
settings = get_settings()

app = FastAPI(title="CB Failed Assistant", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(uploads_router)
app.include_router(jobs_router)
app.include_router(results_router)
app.include_router(export_router)


@app.on_event("startup")
def cleanup_on_startup() -> None:
    job_repository.cleanup_expired()


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

