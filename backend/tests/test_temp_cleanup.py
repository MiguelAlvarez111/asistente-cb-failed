from datetime import UTC, datetime, timedelta

from backend.app.core.config import Settings
from backend.app.repositories.job_repository import JobRepository


def test_temp_cleanup_removes_expired_upload(tmp_path) -> None:
    settings = Settings()
    settings.temp_file_ttl_minutes = 1
    repo = JobRepository(settings)
    upload_dir = tmp_path / "upload"
    upload_dir.mkdir()
    upload = repo.create_upload("u1", upload_dir)
    upload.created_at = datetime.now(UTC) - timedelta(minutes=5)
    removed = repo.cleanup_expired()
    assert removed == 1
    assert not upload_dir.exists()

