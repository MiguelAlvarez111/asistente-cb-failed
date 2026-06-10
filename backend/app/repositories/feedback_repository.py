from collections import Counter
from datetime import UTC, datetime
from typing import Any


class FeedbackRepository:
    def __init__(self) -> None:
        self.feedback: dict[str, list[dict[str, Any]]] = {}

    def add(self, job_id: str, row_id: str, status: str, manual_correction: str | None, note: str | None) -> dict[str, Any]:
        record = {
            "job_id": job_id,
            "row_id": row_id,
            "status": status,
            "manual_correction": manual_correction,
            "note": note,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.feedback.setdefault(job_id, []).append(record)
        return record

    def counts(self, job_id: str) -> dict[str, int]:
        return dict(Counter(item["status"] for item in self.feedback.get(job_id, [])))

    def clear(self, job_id: str) -> None:
        self.feedback.pop(job_id, None)


feedback_repository = FeedbackRepository()
