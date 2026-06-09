from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from backend.app.schemas.files import FileKind


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class RowWorkStatus(StrEnum):
    PENDING = "Pending"
    COPIED = "Copied"
    APPLIED = "Applied"
    SKIPPED = "Skipped"


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upload_id: str
    file_overrides: dict[str, FileKind] = {}


class JobCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: JobStatus


class JobSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_rows: int = 0
    malformed_rows: int = 0
    ignored_rows: int = 0
    final_action_counts: dict[str, int] = {}
    confidence_counts: dict[str, int] = {}
    work_status_counts: dict[str, int] = {}
    manual_review_count: int = 0
    ai_rows_count: int = 0


class JobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: JobStatus
    progress: float
    message: str
    summary: JobSummary


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    manual_correction: str | None = None
    note: str | None = None


class WorkStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RowWorkStatus


class WorkStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_id: str
    status: RowWorkStatus
