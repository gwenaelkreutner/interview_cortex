import logging
import uuid

from clients.base import TraceContext

logger = logging.getLogger(__name__)


class WeaveClient:
    """
    Stub implementation of the Weave observability client.
    Replace with real weave.init() + weave.op() calls in production.

    In production:
        import weave
        weave.init(project_name)
        # Use @weave.op() decorator or weave.trace() context manager
    """

    def __init__(self, project_name: str):
        self._project = project_name
        logger.info(f"[WeaveClient] initialized (project={project_name})")

    def start_trace(self, name: str, metadata: dict) -> TraceContext:
        trace_id = str(uuid.uuid4())
        logger.info(f"[Weave] ▶ START  trace={name!r} id={trace_id[:8]} metadata={metadata}")
        return TraceContext(trace_id=trace_id, name=name, metadata=metadata)

    def end_trace(self, ctx: TraceContext, status: str, result_metadata: dict | None = None) -> None:
        logger.info(
            f"[Weave] ■ END    trace={ctx.name!r} id={ctx.trace_id[:8]} "
            f"status={status} result={result_metadata}"
        )

    def log_event(self, ctx: TraceContext, event: str, data: dict) -> None:
        logger.info(f"[Weave] ● EVENT  trace={ctx.name!r} id={ctx.trace_id[:8]} event={event!r} data={data}")
