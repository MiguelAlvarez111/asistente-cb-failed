from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.core.security import require_auth
from backend.app.repositories.job_repository import job_repository
from backend.app.repositories.work_status_repository import work_status_repository
from backend.app.schemas.results import LookupCellColors, LookupCurrentValues, LookupRecommendedValues, RowDetail, RowResult, SINLookupMatch, SINLookupResponse
from backend.app.services.sin_lookup import normalize_sin

router = APIRouter(prefix="/api/results", tags=["results"], dependencies=[Depends(require_auth)])


def _provider_summary(last_title: str, first: str) -> str:
    return " ".join(part for part in [last_title, first] if part).strip()


def _sync_work_status(job_id: str, row: RowDetail) -> RowDetail:
    row.Work_Status = work_status_repository.get(job_id, row.row_id)
    return row


def _to_lookup_match(row: RowDetail) -> SINLookupMatch:
    return SINLookupMatch(
        row_id=row.row_id,
        sin=row.SIN,
        region=row.Region or row.sheet_name,
        row_index=row.Row_Index,
        final_action=row.Final_Action,
        quick_action=row.Quick_Action,
        apply_this=row.Apply_This,
        work_status=row.Work_Status,
        current_provider=_provider_summary(row.Current_Last_Title, row.Current_First),
        current=LookupCurrentValues(
            last_title=row.Current_Last_Title,
            first=row.Current_First,
            npi=row.Current_NPI,
            cbcode=row.Current_CBCode,
        ),
        recommended=LookupRecommendedValues(
            last_title=row.Recommended_Last_Title,
            first=row.Recommended_First,
            npi=row.Recommended_NPI,
            cbcode=row.Recommended_CBCode,
            comments=row.Recommended_Comments,
            source=row.Recommended_Source,
        ),
        cell_colors=LookupCellColors(
            last_title=row.Cell_Color_Last_Title,
            first=row.Cell_Color_First,
            npi=row.Cell_Color_NPI,
            cbcode=row.Cell_Color_CBCode,
            comments=row.Cell_Color_Comments,
            source=row.Cell_Color_Source,
        ),
        correction_summary=row.Correction_Summary,
        analyst_next_step=row.Analyst_Next_Step,
        validation_status=row.Validation_Status,
        manual_reason=row.Manual_Reason or None,
    )


@router.get("/{job_id}", response_model=list[RowResult])
def get_results(job_id: str) -> list[RowResult]:
    job = job_repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or expired")
    return [RowResult(**_sync_work_status(job_id, row).model_dump(exclude={"deterministic_interpretation", "ai_interpretation", "validation"})) for row in job.rows]


@router.get("/{job_id}/lookup", response_model=SINLookupResponse)
def lookup_by_sin(job_id: str, sin: str = Query(..., min_length=1)) -> SINLookupResponse:
    job = job_repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or expired")
    normalized_query = normalize_sin(sin)
    matches = [
        _to_lookup_match(_sync_work_status(job_id, row))
        for row in job.rows
        if normalize_sin(row.SIN) == normalized_query
    ]
    return SINLookupResponse(query=sin, normalized_query=normalized_query, match_count=len(matches), matches=matches)


@router.get("/{job_id}/rows/{row_id}", response_model=RowDetail)
def get_row_detail(job_id: str, row_id: str) -> RowDetail:
    job = job_repository.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found or expired")
    for row in job.rows:
        if row.row_id == row_id:
            return _sync_work_status(job_id, row)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Row not found")
