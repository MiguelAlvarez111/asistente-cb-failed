import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from backend.app.core.config import Settings, get_settings
from backend.app.core.security import require_auth
from backend.app.repositories.job_repository import StoredFile, job_repository
from backend.app.schemas.files import FileKind, UploadInspectionResponse
from backend.app.services.file_classifier import inspect_file

router = APIRouter(prefix="/api/uploads", tags=["uploads"], dependencies=[Depends(require_auth)])


@router.post("/inspect", response_model=UploadInspectionResponse)
async def inspect_uploads(
    files: list[UploadFile] = File(...),
    settings: Settings = Depends(get_settings),
) -> UploadInspectionResponse:
    job_repository.cleanup_expired()
    upload_id = secrets.token_urlsafe(24)
    upload_dir = settings.temp_root / "uploads" / upload_id
    upload_dir.mkdir(parents=True, exist_ok=False)
    upload = job_repository.create_upload(upload_id, upload_dir)
    inspections = []
    warnings: list[str] = []

    for upload_file in files:
        file_id = secrets.token_urlsafe(12)
        filename = Path(upload_file.filename or f"{file_id}.bin").name
        data = await upload_file.read()
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"{filename} exceeds MAX_UPLOAD_MB={settings.max_upload_mb}.",
            )
        path = upload_dir / f"{file_id}_{filename}"
        path.write_bytes(data)
        inspection = inspect_file(path, file_id, filename)
        if inspection.kind == FileKind.CB_FAILED_REPORT and inspection.row_count > settings.max_rows_per_job:
            warnings.append(f"{filename} exceeds MAX_ROWS_PER_JOB={settings.max_rows_per_job}.")
        job_repository.add_file(upload_id, StoredFile(file_id=file_id, filename=filename, path=str(path), inspection=inspection))
        inspections.append(inspection)

    if not any(item.kind.value == "CB_FAILED_REPORT" for item in inspections):
        warnings.append("No CB Failed report was detected.")
    if not any(item.kind.value == "DICTIONARY" for item in inspections):
        warnings.append("No provider dictionary was detected.")
    return UploadInspectionResponse(upload_id=upload.upload_id, files=inspections, warnings=warnings)
