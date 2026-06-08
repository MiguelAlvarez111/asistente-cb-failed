from datetime import UTC, datetime
from typing import Any


class AuditRepository:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def add(self, record: dict[str, Any]) -> None:
        sanitized = {key: value for key, value in record.items() if key not in {"rows", "original_rows", "patientLast", "patientFirst", "DOB", "AccNumber"}}
        sanitized["timestamp"] = datetime.now(UTC).isoformat()
        self.records.append(sanitized)


audit_repository = AuditRepository()

