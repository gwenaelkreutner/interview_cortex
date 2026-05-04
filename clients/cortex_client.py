import logging
import uuid

from clients.base import CortexCallError, CortexClientProtocol, CortexResponse

logger = logging.getLogger(__name__)


class CortexClient(CortexClientProtocol):
    """
    Stub implementation of the Cortex Agent client.
    Replace with the real Snowflake Cortex client library in production.

    In production this would POST to the Cortex REST endpoint:
        POST /api/v2/cortex/inference:complete
    with the user context and question as payload.
    """

    def __init__(self, base_url: str, api_key: str):
        self._base_url = base_url
        logger.info(f"[CortexClient] initialized (base_url={base_url})")

    def call_agent(self, user_context: dict, question: str) -> CortexResponse:
        user_id = user_context.get("user_id", "unknown")
        logger.info(f"[CortexClient] Calling agent for user={user_id} | question={question[:80]}...")

        response_text = (
            f"As a {user_context.get('persona')} at {user_context.get('brand')}, "
            f"here is your personalized weekly insight for the question "
            f"'{question}': [Cortex AI-generated content would appear here.]"
        )
        return CortexResponse(
            response_text=response_text,
            trace_id=str(uuid.uuid4()),
            tokens_used=128,
        )
