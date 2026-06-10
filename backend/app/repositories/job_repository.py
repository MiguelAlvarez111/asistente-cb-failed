import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.app.core.config import Settings, get_settings
from backend.app.schemas.files import FileInspection
from backend.app.schemas.jobs import JobStatus, JobSummary
from backend.app.schemas.results import RowDetail
from backend.app.repositories.work_status_repository import work_status_repository


@dataclass
class StoredFile:
    file_id: str
    filename: str
    path: str
    inspection: FileInspection


@dataclass
class UploadRecord:
    upload_id: str
    created_at: datetime
    temp_dir: str
    files: list[StoredFile] = field(default_factory=list)


@dataclass
class JobRecord:
    job_id: str
    upload_id: str
    created_at: datetime
    updated_at: datetime
    temp_dir: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0
    message: str = "Queued"
    summary: JobSummary = field(default_factory=JobSummary)
    rows: list[RowDetail] = field(default_factory=list)
    full_export_path: str | None = None
    audit: dict[str, Any] = field(default_factory=dict)


class JobRepository:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.uploads: dict[str, UploadRecord] = {}
        self.jobs: dict[str, JobRecord] = {}

    def create_upload(self, upload_id: str, temp_dir: Path) -> UploadRecord:
        record = UploadRecord(upload_id=upload_id, created_at=datetime.now(UTC), temp_dir=str(temp_dir))
        self.uploads[upload_id] = record
        return record

    def add_file(self, upload_id: str, stored_file: StoredFile) -> None:
        self.uploads[upload_id].files.append(stored_file)

    def get_upload(self, upload_id: str) -> UploadRecord | None:
        return self.uploads.get(upload_id)

    def create_job(self, job_id: str, upload_id: str, temp_dir: Path) -> JobRecord:
        record = JobRecord(
            job_id=job_id,
            upload_id=upload_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            temp_dir=str(temp_dir),
        )
        self.jobs[job_id] = record
        return record

    def get_job(self, job_id: str) -> JobRecord | None:
        return self.jobs.get(job_id)

    def update_job(self, job_id: str, **changes: Any) -> None:
        job = self.jobs[job_id]
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = datetime.now(UTC)

    def persist_rows(self, job_id: str) -> None:
        job = self.jobs[job_id]
        path = Path(job.temp_dir) / "sanitized_results.json"
        path.write_text(json.dumps([row.model_dump(mode="json") for row in job.rows], indent=2), encoding="utf-8")

    def cleanup_expired(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(minutes=self.settings.temp_file_ttl_minutes)
        removed = 0
        for upload_id, upload in list(self.uploads.items()):
            if upload.created_at < cutoff:
                shutil.rmtree(upload.temp_dir, ignore_errors=True)
                self.uploads.pop(upload_id, None)
                removed += 1
        for job_id, job in list(self.jobs.items()):
            if job.created_at < cutoff:
                shutil.rmtree(job.temp_dir, ignore_errors=True)
                work_status_repository.clear(job_id)
                job.status = JobStatus.EXPIRED
                self.jobs.pop(job_id, None)
                removed += 1
        return removed

    def delete_job_files(self, job_id: str) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        shutil.rmtree(job.temp_dir, ignore_errors=True)
        work_status_repository.clear(job_id)
        upload = self.uploads.pop(job.upload_id, None)
        if upload:
            shutil.rmtree(upload.temp_dir, ignore_errors=True)

    def delete_job(self, job_id: str) -> bool:
        if job_id not in self.jobs:
            return False
        self.delete_job_files(job_id)
        self.jobs.pop(job_id, None)
        return True


job_repository = JobRepository()
