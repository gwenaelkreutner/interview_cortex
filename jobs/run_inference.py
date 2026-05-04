"""
Inference job entry point.

Usage:
    python -m jobs.run_inference                  # runs for today
    python -m jobs.run_inference --date 2026-04-28

Exit code:
    0  all users processed without failure
    1  one or more users failed
"""

import argparse
import logging
import sys
from datetime import date

from clients.cortex_client import CortexClient
from clients.snowflake_client import SnowflakeClient
from clients.weave_client import WeaveClient
from config.settings import get_settings
from observability.tracing import init_tracer
from repositories.insight_repository import InsightRepository
from repositories.mapping_repository import MappingRepository
from repositories.user_repository import UserRepository
from services.insight_service import InsightService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_date() -> date:
    parser = argparse.ArgumentParser(description="Run AI inference batch")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=date.today(),
        help="Logical batch date (YYYY-MM-DD). Defaults to today.",
    )
    return parser.parse_args().date


def _seed_demo_data(snowflake: SnowflakeClient) -> None:
    """Populates in-memory stub with sample data for local demonstration."""
    snowflake.seed("users", [
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
            "persona": "Manager",
            "is_active": True,
        },
    ])
    snowflake.seed("brand_persona_mappings", [
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
                "Which key data trends should {user_name} focus on "
                "for {brand} this week?"
            ),
            "is_active": True,
        },
        # note: no mapping for (BrandA, Manager) — demonstrates graceful failure handling
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
    _seed_demo_data(snowflake)

    cortex = CortexClient(
        base_url=settings.CORTEX_AGENT_BASE_URL,
        api_key=settings.CORTEX_AGENT_API_KEY,
    )
    weave = WeaveClient(project_name=settings.WEAVE_PROJECT_NAME)
    init_tracer(weave)

    service = InsightService(
        user_repo=UserRepository(snowflake),
        mapping_repo=MappingRepository(snowflake),
        insight_repo=InsightRepository(snowflake),
        cortex_client=cortex,
        weave_client=weave,
        max_retries=settings.MAX_RETRIES,
        batch_concurrency=settings.BATCH_CONCURRENCY,
    )

    summary = service.run_batch(batch_date)
    sys.exit(0 if summary.failed == 0 else 1)


if __name__ == "__main__":
    main()
