from fastapi.testclient import TestClient

from backend.app.core.config import get_settings
from backend.app.main import app


def test_protected_route_requires_auth_in_production() -> None:
    settings = get_settings()
    old_env, old_password = settings.app_env, settings.app_password
    settings.app_env = "production"
    settings.app_password = "secret"
    try:
        client = TestClient(app)
        response = client.get("/api/jobs/missing")
        assert response.status_code == 401
    finally:
        settings.app_env = old_env
        settings.app_password = old_password


def test_max_upload_limit() -> None:
    settings = get_settings()
    old_limit = settings.max_upload_mb
    settings.max_upload_mb = 0
    try:
        client = TestClient(app)
        response = client.post("/api/uploads/inspect", files=[("files", ("sample.txt", b"x", "text/plain"))])
        assert response.status_code == 413
    finally:
        settings.max_upload_mb = old_limit

