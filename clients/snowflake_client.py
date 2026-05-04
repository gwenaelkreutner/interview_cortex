import logging

from clients.base import SnowflakeClientProtocol

logger = logging.getLogger(__name__)


class SnowflakeClient(SnowflakeClientProtocol):
    """
    In-memory stub that mimics Snowflake for local development.
    Replace with real snowflake-connector-python in production.

    Usage:
        client = SnowflakeClient(...)
        client.seed("users", [...])
        client.seed("brand_persona_mappings", [...])
    """

    def __init__(self, account: str, user: str, password: str, database: str, schema: str, warehouse: str):
        logger.info(f"[SnowflakeClient] stub initialized (account={account}, db={database})")
        self._tables: dict[str, list[dict]] = {
            "users": [],
            "brand_persona_mappings": [],
            "insight_runs": [],
            "delivery_records": [],
        }

    def seed(self, table: str, rows: list[dict]) -> None:
        self._tables[table] = list(rows)

    def execute_query(self, sql: str, params: dict | None = None) -> list[dict]:
        params = params or {}
        sql_upper = " ".join(sql.split()).upper()
        logger.debug(f"[SnowflakeClient] SQL: {sql_upper[:120]}")

        if sql_upper.startswith("MERGE INTO INSIGHT_RUNS"):
            return self._merge_insight_run(params)
        if sql_upper.startswith("MERGE INTO DELIVERY_RECORDS"):
            return self._merge_delivery_record(params)
        if sql_upper.startswith("UPDATE INSIGHT_RUNS"):
            return self._update_insight_run(sql_upper, params)
        if sql_upper.startswith("UPDATE DELIVERY_RECORDS"):
            return self._update_delivery_record(sql_upper, params)
        if "FROM BRAND_PERSONA_MAPPINGS" in sql_upper:
            return self._select_mappings(params)
        if "FROM USERS" in sql_upper:
            return self._select_users(sql_upper, params)
        if "FROM INSIGHT_RUNS IR" in sql_upper or (
            "FROM INSIGHT_RUNS" in sql_upper and "DELIVERY_RECORDS" in sql_upper
        ):
            return self._select_completed_without_delivery(params)
        if "FROM INSIGHT_RUNS" in sql_upper:
            return self._select_insight_runs(sql_upper, params)
        if "FROM DELIVERY_RECORDS" in sql_upper:
            return self._select_delivery_records(params)
        return []

    def execute_many(self, sql: str, rows: list[dict]) -> None:
        logger.debug(f"[SnowflakeClient] BATCH INSERT: {len(rows)} rows")

    def close(self) -> None:
        logger.info("[SnowflakeClient] Connection closed")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    # --- private query handlers ---

    def _select_users(self, sql: str, params: dict) -> list[dict]:
        rows = [r for r in self._tables["users"] if r.get("is_active", True)]
        if "WHERE USER_ID =" in sql or "WHERE USER_ID=" in sql:
            uid = params.get("user_id")
            rows = [r for r in rows if r["user_id"] == uid]
        return rows

    def _select_mappings(self, params: dict) -> list[dict]:
        brand, persona = params.get("brand"), params.get("persona")
        return [
            r for r in self._tables["brand_persona_mappings"]
            if r["brand"] == brand and r["persona"] == persona and r.get("is_active", True)
        ]

    def _select_insight_runs(self, sql: str, params: dict) -> list[dict]:
        rows = list(self._tables["insight_runs"])
        if "USER_ID =" in sql and "BATCH_DATE =" in sql:
            uid, bd = params.get("user_id"), str(params.get("batch_date", ""))
            rows = [r for r in rows if r["user_id"] == uid and str(r["batch_date"]) == bd]
        return rows

    def _select_completed_without_delivery(self, params: dict) -> list[dict]:
        bd = str(params.get("batch_date", ""))
        completed = [
            r for r in self._tables["insight_runs"]
            if str(r["batch_date"]) == bd and r["status"] == "COMPLETED"
        ]
        sent_run_ids = {
            d["run_id"] for d in self._tables["delivery_records"] if d["status"] == "SENT"
        }
        return [r for r in completed if r["run_id"] not in sent_run_ids]

    def _select_delivery_records(self, params: dict) -> list[dict]:
        run_id = params.get("run_id")
        return [r for r in self._tables["delivery_records"] if r["run_id"] == run_id]

    def _merge_insight_run(self, params: dict) -> list[dict]:
        user_id, batch_date = params.get("user_id"), str(params.get("batch_date", ""))
        exists = any(
            r["user_id"] == user_id and str(r["batch_date"]) == batch_date
            for r in self._tables["insight_runs"]
        )
        if not exists:
            self._tables["insight_runs"].append({
                "run_id": params["run_id"],
                "batch_date": batch_date,
                "user_id": user_id,
                "question": params.get("question", ""),
                "status": "PENDING",
                "ai_response": None,
                "error_message": None,
                "cortex_trace_id": None,
                "weave_trace_id": None,
                "attempt_count": 0,
            })
        return []

    def _merge_delivery_record(self, params: dict) -> list[dict]:
        run_id = params.get("run_id")
        exists = any(r["run_id"] == run_id for r in self._tables["delivery_records"])
        if not exists:
            self._tables["delivery_records"].append({
                "delivery_id": params["delivery_id"],
                "run_id": run_id,
                "user_id": params.get("user_id"),
                "recipient_email": params.get("recipient_email"),
                "status": "PENDING",
                "provider_message_id": None,
                "error_message": None,
                "attempt_count": 0,
                "sent_at": None,
            })
        return []

    def _update_insight_run(self, sql: str, params: dict) -> list[dict]:
        run_id = params.get("run_id")
        row = next((r for r in self._tables["insight_runs"] if r["run_id"] == run_id), None)
        if row is None:
            return []
        if "STATUS = 'IN_PROGRESS'" in sql:
            row["status"] = "IN_PROGRESS"
        elif "STATUS = 'COMPLETED'" in sql:
            row.update(status="COMPLETED", ai_response=params.get("ai_response"),
                       cortex_trace_id=params.get("cortex_trace_id"),
                       weave_trace_id=params.get("weave_trace_id"))
        elif "STATUS = 'FAILED'" in sql:
            row.update(status="FAILED", error_message=params.get("error_message"))
        elif "ATTEMPT_COUNT = ATTEMPT_COUNT + 1" in sql:
            row["attempt_count"] = row.get("attempt_count", 0) + 1
        return []

    def _update_delivery_record(self, sql: str, params: dict) -> list[dict]:
        delivery_id = params.get("delivery_id")
        row = next((r for r in self._tables["delivery_records"] if r["delivery_id"] == delivery_id), None)
        if row is None:
            return []
        if "STATUS = 'SENT'" in sql:
            row.update(status="SENT", provider_message_id=params.get("provider_message_id"))
        elif "STATUS = 'FAILED'" in sql:
            row.update(status="FAILED", error_message=params.get("error_message"))
        elif "ATTEMPT_COUNT = ATTEMPT_COUNT + 1" in sql:
            row["attempt_count"] = row.get("attempt_count", 0) + 1
        return []
