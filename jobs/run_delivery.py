"""
Email delivery job entry point.

Runs independently of the inference job — reads COMPLETED insight runs
that have not yet been delivered and sends emails.

Usage:
    python -m jobs.run_delivery                   # runs for today
    python -m jobs.run_delivery --date 2026-04-28

Exit code:
    0  all deliveries succeeded
    1  one or more deliveries failed
"""

import argparse
import logging
import sys
from datetime import date

from clients.email_client import EmailClient
from clients.snowflake_client import SnowflakeClient
from clients.weave_client import WeaveClient
from config.settings import get_settings
from observability.tracing import init_tracer
from repositories.delivery_repository import DeliveryRepository
from repositories.insight_repository import InsightRepository
from repositories.user_repository import UserRepository
from services.delivery_service import DeliveryService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_date() -> date:
    parser = argparse.ArgumentParser(description="Run email delivery batch")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=date.today(),
        help="Logical batch date (YYYY-MM-DD). Defaults to today.",
    )
    return parser.parse_args().date


def _seed_demo_data(snowflake: SnowflakeClient, batch_date: date) -> None:
    """Pre-populates in-memory stub with COMPLETED insight runs for local demo."""
    snowflake.seed("users", [
        {"user_id": "user-001", "email": "alice@example.com", "full_name": "Alice Durand",
         "brand": "BrandA", "persona": "Executive", "is_active": True},
        {"user_id": "user-002", "email": "bob@example.com", "full_name": "Bob Martin",
         "brand": "BrandB", "persona": "Analyst", "is_active": True},
    ])
    snowflake.seed("insight_runs", [
        {"run_id": "run-001", "batch_date": batch_date.isoformat(), "user_id": "user-001",
         "question": "What are your top priorities?", "status": "COMPLETED",
         "ai_response": "Focus on Q2 OKRs and stakeholder alignment.",
         "cortex_trace_id": "ctx-001", "weave_trace_id": "wtx-001",
         "error_message": None, "attempt_count": 1},
        {"run_id": "run-002", "batch_date": batch_date.isoformat(), "user_id": "user-002",
         "question": "Which data trends matter this week?",  "status": "COMPLETED",
         "ai_response": "Watch conversion rate dips in the EMEA funnel.",
         "cortex_trace_id": "ctx-002", "weave_trace_id": "wtx-002",
         "error_message": None, "attempt_count": 1},
    ])


def main() -> None:
    batch_date = _parse_date()
    settings = get_settings()

    snowflake = SnowflakeClient(
        account=settings.SNOWFLAKE_ACCOUNT,
        user=settings.SNOWFLAKE_USER,
        password=settings.SNOWFLAKE_PASSWORD,
        database=settings.SNOWFLAKE_DATABASE,
        schema=settings.SNOWFLAKE_SCHEMA,
        warehouse=settings.SNOWFLAKE_WAREHOUSE,
    )
    _seed_demo_data(snowflake, batch_date)

    email = EmailClient(
        from_address=settings.EMAIL_FROM_ADDRESS,
        provider=settings.EMAIL_PROVIDER,
    )
    weave = WeaveClient(project_name=settings.WEAVE_PROJECT_NAME)
    init_tracer(weave)

    service = DeliveryService(
        insight_repo=InsightRepository(snowflake),
        delivery_repo=DeliveryRepository(snowflake),
        user_repo=UserRepository(snowflake),
        email_client=email,
        weave_client=weave,
        max_retries=settings.MAX_RETRIES,
        batch_concurrency=settings.BATCH_CONCURRENCY,
    )

    summary = service.run_batch(batch_date)
    sys.exit(0 if summary.failed == 0 else 1)


if __name__ == "__main__":
    main()
