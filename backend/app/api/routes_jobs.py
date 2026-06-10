import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import require_auth
from backend.app.repositories.feedback_repository import feedback_repository
from backend.app.repositories.job_repository import job_repository
from backend.app.repositories.work_status_repository import work_status_repository
from backend.app.schemas.files import FileKind
from backend.app.schemas.jobs import FeedbackRequest, JobCreateRequest, JobCreateResponse, JobStatus, JobStatusResponse, WorkStatusRequest, WorkStatusResponse
from backend.app.services.job_runner import BackgroundTasksJobRunner
from backend.app.services.report_processor import report_processor

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(require_auth)])


OVERRIDABLE_KINDS = {FileKind.CB_FAILED_REPORT, FileKind.CORRECTIONS, FileKind.DICTIONARY, FileKind.IGNORE}


def _apply_file_overrides(payload: JobCreateRequest) -> None:
    upload = job_repository.get_upload(payload.upload_id)
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found or expired")
    files_by_id = {item.file_id: item for item in upload.files}
    for file_id, kind in payload.file_overrides.items():
        if file_id not in files_by_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown file_id override: {file_id}")
        if kind not in OVERRIDABLE_KINDS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported file type override: {kind}")
        stored = files_by_id[file_id]
        stored.inspection = stored.inspection.model_copy(update={"kind": kind})


@router.post("", response_model=JobCreateResponse)
def create_job(
    payload: JobCreateRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
) -> JobCreateResponse:
    upload = job_repository.get_upload(payload.upload_id)
    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found or expired")
    _apply_file_overrides(payload)
    job_id = secrets.token_urlsafe(24)
    job_dir = settings.temp_root / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    job = job_repository.create_job(job_id, payload.upload_id, job_dir)
    BackgroundTasksJobRunner(background_tasks).enqueue(job_id, payload.upload_id, report_processor.process)
    return JobCreateResponse(job_id=job.job_id, status=JobStatus.QUEUED)


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> JobStatusResponse:
    job = job_repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or expired")
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        message=job.message,
        summary=job.summary,
    )


@router.delete("/{job_id}")
def clear_job(job_id: str) -> dict[str, str]:
    if not job_repository.get_job(job_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or expired")
    job_repository.delete_job(job_id)
    feedback_repository.clear(job_id)
    return {"status": "cleared"}


@router.post("/{job_id}/feedback/{row_id}")
def add_feedback(job_id: str, row_id: str, payload: FeedbackRequest) -> dict[str, str]:
    job = job_repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or expired")
    feedback_repository.add(job_id, row_id, payload.status, payload.manual_correction, payload.note)
    job.audit["user_feedback_counts"] = feedback_repository.counts(job_id)
    return {"status": "ok"}


@router.put("/{job_id}/rows/{row_id}/work-status", response_model=WorkStatusResponse)
def update_work_status(job_id: str, row_id: str, payload: WorkStatusRequest) -> WorkStatusResponse:
    job = job_repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or expired")
    row = next((item for item in job.rows if item.row_id == row_id), None)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
    row.Work_Status = work_status_repository.set(job_id, row_id, payload.status)
    job.summary.work_status_counts = work_status_repository.counts(job_id)
    return WorkStatusResponse(row_id=row_id, status=row.Work_Status)
