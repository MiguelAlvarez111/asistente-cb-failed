from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from backend.app.core.security import require_auth
from backend.app.repositories.job_repository import job_repository
from backend.app.services.excel_exporter import rows_to_workbook

router = APIRouter(prefix="/api/export", tags=["export"], dependencies=[Depends(require_auth)])


@router.get("/{job_id}")
def export_job(
    job_id: str,
    kind: str = Query("full", pattern="^(full|manual_review|high_confidence|summary)$"),
) -> Response:
    job = job_repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or expired")
    if kind == "full":
        if not job.full_export_path or not Path(job.full_export_path).exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Full export is unavailable")
        data = Path(job.full_export_path).read_bytes()
        filename = f"cb_failed_{job_id}_full.xlsx"
        job_repository.delete_job_files(job_id)
    else:
        data = rows_to_workbook(job.rows, kind=kind)
        filename = f"cb_failed_{job_id}_{kind}.xlsx"
    return Response(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

