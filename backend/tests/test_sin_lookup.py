from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.repositories.feedback_repository import feedback_repository
from backend.app.repositories.job_repository import job_repository
from backend.app.repositories.work_status_repository import work_status_repository
from backend.app.schemas.ai import AIAction, AIInterpretation, AIReasonCode
from backend.app.schemas.jobs import RowWorkStatus
from backend.app.schemas.results import RowDetail, ValidationResult, ValidationStatus


def _interp() -> AIInterpretation:
    return AIInterpretation(
        action=AIAction.COMPLETE_INFO,
        reason_code=AIReasonCode.DIRECT_NPI,
        target_provider_name=None,
        target_npi="1234567890",
        target_cbcode=None,
        requires_add_to_ge=False,
        is_pending_usap=False,
        confidence=1,
        needs_manual_review=False,
        explanation="ok",
    )


def _row(row_id: str, sin: str, region: str = "MARYLAND") -> RowDetail:
    interp = _interp()
    validation = ValidationResult(status=ValidationStatus.CBCODE_FOUND, details="ok", matches=[], npi_registry_name=None, needs_manual_review=False)
    return RowDetail(
        row_id=row_id,
        sheet_name=region,
        SIN=sin,
        Region=region,
        Row_Index=8,
        sanitized_original={"last_title": "DOE"},
        Bot_Accion="COMPLETE_INFO",
        Bot_Suggestion="ok",
        Bot_Details="ok",
        AI_Action="COMPLETE_INFO",
        AI_Reason_Code="DIRECT_NPI",
        AI_Confidence=1,
        Needs_Manual_Review=False,
        Validation_Status="CBCODE_FOUND",
        Validation_Details="ok",
        Dictionary_Match_Type=None,
        Matched_Dictionary="Dictionary",
        Matched_NPI="1234567890",
        Matched_CBCode="CB1",
        Matched_Provider_Name="DOE JANE",
        Deactivation_Status=None,
        AI_Explanation="ok",
        Final_Action="COMPLETE_INFO",
        Final_Recommendation="Apply values.",
        Quick_Action="Complete fields",
        Apply_This="YES",
        Current_Last_Title="DOE",
        Current_First="JANE",
        Current_NPI="",
        Current_CBCode="",
        Recommended_Last_Title="DOE",
        Recommended_First="JANE",
        Recommended_NPI="1234567890",
        Recommended_CBCode="CB1",
        Recommended_Source="Dictionary",
        Correction_Summary="Complete missing values.",
        Analyst_Next_Step="Apply the recommended values.",
        Cell_Color_NPI="green",
        Cell_Color_CBCode="green",
        Cell_Color_Source="green",
        deterministic_interpretation=interp,
        ai_interpretation=interp,
        validation=validation,
    )


def _seed_job(job_id: str, rows: list[RowDetail]) -> None:
    job = job_repository.jobs[job_id]
    job.rows = rows


def test_sin_lookup_exact_match(tmp_path) -> None:
    job_repository.create_job("lookup-exact", "upload", tmp_path)
    _seed_job("lookup-exact", [_row("r1", "abc 123")])
    client = TestClient(app)

    response = client.get("/api/results/lookup-exact/lookup", params={"sin": " ABC\n123 "})

    assert response.status_code == 200
    payload = response.json()
    assert payload["match_count"] == 1
    assert payload["matches"][0]["sin"] == "abc 123"
    assert payload["matches"][0]["recommended"]["cbcode"] == "CB1"


def test_sin_lookup_no_match(tmp_path) -> None:
    job_repository.create_job("lookup-none", "upload", tmp_path)
    _seed_job("lookup-none", [_row("r1", "SIN1")])
    client = TestClient(app)

    response = client.get("/api/results/lookup-none/lookup", params={"sin": "missing"})

    assert response.status_code == 200
    assert response.json()["match_count"] == 0


def test_sin_lookup_multiple_matches_and_work_status(tmp_path) -> None:
    job_repository.create_job("lookup-multiple", "upload", tmp_path)
    _seed_job("lookup-multiple", [_row("r1", "SIN1", "MARYLAND"), _row("r2", "sin1", "NY")])
    work_status_repository.set("lookup-multiple", "r2", RowWorkStatus.COPIED)
    client = TestClient(app)

    response = client.get("/api/results/lookup-multiple/lookup", params={"sin": " sin1 "})

    assert response.status_code == 200
    payload = response.json()
    assert payload["match_count"] == 2
    assert {match["region"] for match in payload["matches"]} == {"MARYLAND", "NY"}
    assert any(match["work_status"] == "Copied" for match in payload["matches"])


def test_work_status_update(tmp_path) -> None:
    job_repository.create_job("work-status", "upload", tmp_path)
    _seed_job("work-status", [_row("r1", "SIN1")])
    client = TestClient(app)

    response = client.put("/api/jobs/work-status/rows/r1/work-status", json={"status": "Applied"})

    assert response.status_code == 200
    assert response.json()["status"] == "Applied"
    assert job_repository.get_job("work-status").rows[0].Work_Status == RowWorkStatus.APPLIED


def test_delete_job_clears_temp_state(tmp_path) -> None:
    upload_dir = tmp_path / "upload"
    job_dir = tmp_path / "job"
    upload_dir.mkdir()
    job_dir.mkdir()
    (upload_dir / "source.xlsx").write_text("source", encoding="utf-8")
    (job_dir / "processed.xlsx").write_text("processed", encoding="utf-8")
    job_repository.create_upload("clear-upload", upload_dir)
    job_repository.create_job("clear-job", "clear-upload", job_dir)
    _seed_job("clear-job", [_row("r1", "SIN1")])
    work_status_repository.set("clear-job", "r1", RowWorkStatus.COPIED)
    feedback_repository.add("clear-job", "r1", "accepted", None, None)
    client = TestClient(app)

    response = client.delete("/api/jobs/clear-job")

    assert response.status_code == 200
    assert response.json() == {"status": "cleared"}
    assert job_repository.get_job("clear-job") is None
    assert job_repository.get_upload("clear-upload") is None
    assert work_status_repository.counts("clear-job") == {}
    assert feedback_repository.counts("clear-job") == {}
    assert not upload_dir.exists()
    assert not job_dir.exists()
