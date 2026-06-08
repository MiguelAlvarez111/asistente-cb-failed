from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.security import require_auth
from backend.app.repositories.job_repository import job_repository
from backend.app.schemas.results import RowDetail, RowResult

router = APIRouter(prefix="/api/results", tags=["results"], dependencies=[Depends(require_auth)])


@router.get("/{job_id}", response_model=list[RowResult])
def get_results(job_id: str) -> list[RowResult]:
    job = job_repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or expired")
    return [RowResult(**row.model_dump(exclude={"deterministic_interpretation", "ai_interpretation", "validation"})) for row in job.rows]


@router.get("/{job_id}/rows/{row_id}", response_model=RowDetail)
def get_row_detail(job_id: str, row_id: str) -> RowDetail:
    job = job_repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or expired")
    for row in job.rows:
        if row.row_id == row_id:
            return row
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")

