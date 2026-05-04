from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


@dataclass
class DeliveryRecord:
    delivery_id: str
    run_id: str
    user_id: str
    recipient_email: str
    status: DeliveryStatus = DeliveryStatus.PENDING
    provider_message_id: Optional[str] = None
    error_message: Optional[str] = None
    attempt_count: int = 0
    sent_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: dict) -> "DeliveryRecord":
        return cls(
            delivery_id=row["delivery_id"],
            run_id=row["run_id"],
            user_id=row["user_id"],
            recipient_email=row["recipient_email"],
            status=DeliveryStatus(row["status"]),
            provider_message_id=row.get("provider_message_id"),
            error_message=row.get("error_message"),
            attempt_count=row.get("attempt_count", 0),
            sent_at=row.get("sent_at"),
        )

    def is_retryable(self, max_retries: int) -> bool:
        return self.status == DeliveryStatus.FAILED and self.attempt_count < max_retries
