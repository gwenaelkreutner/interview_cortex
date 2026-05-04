import uuid

from clients.base import SnowflakeClientProtocol
from models.delivery import DeliveryRecord


class DeliveryRepository:
    def __init__(self, client: SnowflakeClientProtocol):
        self._client = client

    def get_or_create_delivery(
        self, run_id: str, user_id: str, recipient_email: str
    ) -> tuple[DeliveryRecord, bool]:
        """
        Atomically creates a delivery record for a given run_id if one does not exist.
        Idempotent: safe to call multiple times for the same run_id.
        """
        new_delivery_id = str(uuid.uuid4())
        self._client.execute_query(
            """
            MERGE INTO delivery_records AS target
            USING (SELECT %(run_id)s AS run_id) AS source
            ON target.run_id = source.run_id
            WHEN NOT MATCHED THEN
                INSERT (delivery_id, run_id, user_id, recipient_email, status,
                        attempt_count, created_at, updated_at)
                VALUES (%(delivery_id)s, %(run_id)s, %(user_id)s, %(recipient_email)s,
                        'PENDING', 0, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
            """,
            {"delivery_id": new_delivery_id, "run_id": run_id,
             "user_id": user_id, "recipient_email": recipient_email},
        )
        rows = self._client.execute_query(
            "SELECT * FROM delivery_records WHERE run_id = %(run_id)s",
            {"run_id": run_id},
        )
        record = DeliveryRecord.from_row(rows[0])
        return record, record.delivery_id == new_delivery_id

    def increment_attempt(self, delivery_id: str) -> None:
        self._client.execute_query(
            "UPDATE delivery_records SET attempt_count = attempt_count + 1, "
            "updated_at = CURRENT_TIMESTAMP() WHERE delivery_id = %(delivery_id)s",
            {"delivery_id": delivery_id},
        )

    def mark_sent(self, delivery_id: str, provider_message_id: str) -> None:
        self._client.execute_query(
            """
            UPDATE delivery_records
            SET status              = 'SENT',
                provider_message_id = %(provider_message_id)s,
                sent_at             = CURRENT_TIMESTAMP(),
                updated_at          = CURRENT_TIMESTAMP()
            WHERE delivery_id = %(delivery_id)s
            """,
            {"delivery_id": delivery_id, "provider_message_id": provider_message_id},
        )

    def mark_failed(self, delivery_id: str, error_message: str) -> None:
        self._client.execute_query(
            "UPDATE delivery_records SET status = 'FAILED', "
            "error_message = %(error_message)s, updated_at = CURRENT_TIMESTAMP() "
            "WHERE delivery_id = %(delivery_id)s",
            {"delivery_id": delivery_id, "error_message": error_message},
        )
