from collections import Counter

from backend.app.schemas.jobs import RowWorkStatus


class WorkStatusRepository:
    def __init__(self) -> None:
        self.statuses: dict[str, dict[str, RowWorkStatus]] = {}

    def get(self, job_id: str, row_id: str) -> RowWorkStatus:
        return self.statuses.get(job_id, {}).get(row_id, RowWorkStatus.PENDING)

    def set(self, job_id: str, row_id: str, status: RowWorkStatus) -> RowWorkStatus:
        self.statuses.setdefault(job_id, {})[row_id] = status
        return status

    def counts(self, job_id: str) -> dict[str, int]:
        return dict(Counter(status.value for status in self.statuses.get(job_id, {}).values()))

    def clear(self, job_id: str) -> None:
        self.statuses.pop(job_id, None)


work_status_repository = WorkStatusRepository()
