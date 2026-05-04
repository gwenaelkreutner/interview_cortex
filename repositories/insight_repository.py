import uuid
from datetime import date

from clients.base import SnowflakeClientProtocol
from models.insight import InsightRun


class InsightRepository:
    def __init__(self, client: SnowflakeClientProtocol):
        self._client = client

    def get_or_create_run(self, user_id: str, question: str, batch_date: date) -> tuple[InsightRun, bool]:
        """
        Atomically creates an insight run row for (user_id, batch_date) if it does not
        already exist. Returns (run, created) where created=True means a new row was
        inserted. Idempotent: safe to call multiple times for the same arguments.
        """
        new_run_id = str(uuid.uuid4())
        self._client.execute_query(
            """
            MERGE INTO insight_runs AS target
            USING (SELECT %(user_id)s AS user_id, %(batch_date)s AS batch_date) AS source
            ON target.user_id = source.user_id AND target.batch_date = source.batch_date
            WHEN NOT MATCHED THEN
                INSERT (run_id, batch_date, user_id, question, status, attempt_count,
                        created_at, updated_at)
                VALUES (%(run_id)s, %(batch_date)s, %(user_id)s, %(question)s,
                        'PENDING', 0, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())
            """,
            {"run_id": new_run_id, "user_id": user_id,
             "batch_date": batch_date.isoformat(), "question": question},
        )
        rows = self._client.execute_query(
            "SELECT * FROM insight_runs "
            "WHERE user_id = %(user_id)s AND batch_date = %(batch_date)s",
            {"user_id": user_id, "batch_date": batch_date.isoformat()},
        )
        run = InsightRun.from_row(rows[0])
        return run, run.run_id == new_run_id

    def mark_in_progress(self, run_id: str) -> None:
        self._client.execute_query(
            "UPDATE insight_runs SET status = 'IN_PROGRESS', "
            "updated_at = CURRENT_TIMESTAMP() WHERE run_id = %(run_id)s",
            {"run_id": run_id},
        )

    def increment_attempt(self, run_id: str) -> None:
        self._client.execute_query(
            "UPDATE insight_runs SET attempt_count = attempt_count + 1, "
            "updated_at = CURRENT_TIMESTAMP() WHERE run_id = %(run_id)s",
            {"run_id": run_id},
        )

    def save_completed(
        self,
        run_id: str,
        ai_response: str,
        cortex_trace_id: str,
        weave_trace_id: str,
    ) -> None:
        self._client.execute_query(
            """
            UPDATE insight_runs
            SET status = 'COMPLETED',
                ai_response      = %(ai_response)s,
                cortex_trace_id  = %(cortex_trace_id)s,
                weave_trace_id   = %(weave_trace_id)s,
                updated_at       = CURRENT_TIMESTAMP()
            WHERE run_id = %(run_id)s
            """,
            {"run_id": run_id, "ai_response": ai_response,
             "cortex_trace_id": cortex_trace_id, "weave_trace_id": weave_trace_id},
        )

    def save_failed(self, run_id: str, error_message: str) -> None:
        self._client.execute_query(
            "UPDATE insight_runs SET status = 'FAILED', "
            "error_message = %(error_message)s, updated_at = CURRENT_TIMESTAMP() "
            "WHERE run_id = %(run_id)s",
            {"run_id": run_id, "error_message": error_message},
        )

    def get_completed_without_delivery(self, batch_date: date) -> list[InsightRun]:
        rows = self._client.execute_query(
            """
            SELECT ir.*
            FROM insight_runs ir
            LEFT JOIN delivery_records dr
                   ON dr.run_id = ir.run_id AND dr.status = 'SENT'
            WHERE ir.batch_date = %(batch_date)s
              AND ir.status     = 'COMPLETED'
              AND dr.delivery_id IS NULL
            """,
            {"batch_date": batch_date.isoformat()},
        )
        return [InsightRun.from_row(row) for row in rows]
