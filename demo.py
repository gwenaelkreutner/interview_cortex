"""
End-to-end demo using the in-memory Snowflake stub.

Runs the inference job then the delivery job against the same in-memory
store, so you can see the full flow without a real Snowflake connection.

Usage:
    python demo.py
    python demo.py --date 2026-04-28
"""

import argparse
import logging
from datetime import date

from clients.cortex_client import CortexClient
from clients.email_client import EmailClient
from clients.snowflake_client import SnowflakeClient
from clients.weave_client import WeaveClient
from observability.tracing import init_tracer
from repositories.delivery_repository import DeliveryRepository
from repositories.insight_repository import InsightRepository
from repositories.mapping_repository import MappingRepository
from repositories.user_repository import UserRepository
from services.delivery_service import DeliveryService
from services.insight_service import InsightService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)


USERS = [
    {
        "user_id": "user-001",
        "email": "alice@example.com",
        "full_name": "Alice Durand",
        "brand": "BrandA",
        "persona": "Executive",
        "is_active": True,
    },
    {
        "user_id": "user-002",
        "email": "bob@example.com",
        "full_name": "Bob Martin",
        "brand": "BrandB",
        "persona": "Analyst",
        "is_active": True,
    },
    {
        "user_id": "user-003",
        "email": "carla@example.com",
        "full_name": "Carla Petit",
        "brand": "BrandA",
        "persona": "Manager",  # no mapping → graceful failure
        "is_active": True,
    },
]

MAPPINGS = [
    {
        "mapping_id": "map-001",
        "brand": "BrandA",
        "persona": "Executive",
        "question_template": (
            "What are the top 3 strategic priorities for {user_name} "
            "as an executive at {brand} this week?"
        ),
        "is_active": True,
    },
    {
        "mapping_id": "map-002",
        "brand": "BrandB",
        "persona": "Analyst",
        "question_template": (
            "Which key data trends should {user_name} focus on for {brand} this week?"
        ),
        "is_active": True,
    },
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    batch_date = parser.parse_args().date

    # Shared in-memory store — both jobs read/write to the same instance
    snowflake = SnowflakeClient(
        account="demo", user="demo", password="demo",
        database="demo", schema="demo", warehouse="demo",
    )
    snowflake.seed("users", USERS)
    snowflake.seed("brand_persona_mappings", MAPPINGS)

    weave = WeaveClient(project_name="cortex-demo")
    init_tracer(weave)

    user_repo     = UserRepository(snowflake)
    mapping_repo  = MappingRepository(snowflake)
    insight_repo  = InsightRepository(snowflake)
    delivery_repo = DeliveryRepository(snowflake)

    print("\n" + "=" * 60)
    print(f"  STEP 1 — Inference job  [{batch_date}]")
    print("=" * 60)
    inference = InsightService(
        user_repo=user_repo,
        mapping_repo=mapping_repo,
        insight_repo=insight_repo,
        cortex_client=CortexClient(base_url="https://cortex.example.com", api_key="demo"),
        weave_client=weave,
    )
    inference_summary = inference.run_batch(batch_date)

    print("\n" + "=" * 60)
    print(f"  STEP 2 — Delivery job   [{batch_date}]")
    print("=" * 60)
    delivery = DeliveryService(
        insight_repo=insight_repo,
        delivery_repo=delivery_repo,
        user_repo=user_repo,
        email_client=EmailClient(from_address="insights@example.com"),
        weave_client=weave,
    )
    delivery_summary = delivery.run_batch(batch_date)

    print("\n" + "=" * 60)
    print("  FINAL STATE — insight_runs")
    print("=" * 60)
    for run in snowflake._tables["insight_runs"]:
        print(
            f"  user={run['user_id']}  status={run['status']:<12}"
            f"  attempts={run['attempt_count']}"
        )

    print("\n  FINAL STATE — delivery_records")
    for rec in snowflake._tables["delivery_records"]:
        print(
            f"  run={rec['run_id'][:8]}...  "
            f"email={rec['recipient_email']:<25}  status={rec['status']}"
        )

    print("\n" + "=" * 60)
    print(f"  {inference_summary}")
    print(f"  {delivery_summary}")
    print("=" * 60 + "\n")

    print("Idempotency check: re-running inference for the same date...")
    inference_summary2 = inference.run_batch(batch_date)
    print(f"  {inference_summary2}  ← all skipped, no duplicate Cortex calls\n")


if __name__ == "__main__":
    main()
