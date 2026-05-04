from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional


class InsightStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass
class InsightRun:
    run_id: str
    batch_date: date
    user_id: str
    question: str
    status: InsightStatus = InsightStatus.PENDING
    ai_response: Optional[str] = None
    error_message: Optional[str] = None
    cortex_trace_id: Optional[str] = None
    weave_trace_id: Optional[str] = None
    attempt_count: int = 0

    @classmethod
    def from_row(cls, row: dict) -> "InsightRun":
        batch_date = row["batch_date"]
        if isinstance(batch_date, str):
            batch_date = date.fromisoformat(batch_date)
        return cls(
            run_id=row["run_id"],
            batch_date=batch_date,
            user_id=row["user_id"],
            question=row["question"],
            status=InsightStatus(row["status"]),
            ai_response=row.get("ai_response"),
            error_message=row.get("error_message"),
            cortex_trace_id=row.get("cortex_trace_id"),
            weave_trace_id=row.get("weave_trace_id"),
            attempt_count=row.get("attempt_count", 0),
        )

    def is_retryable(self, max_retries: int) -> bool:
        return self.status == InsightStatus.FAILED and self.attempt_count < max_retries
