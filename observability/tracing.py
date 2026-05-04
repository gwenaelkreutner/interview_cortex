import functools
import logging
from typing import Callable, Optional

from clients.base import TraceContext, WeaveClientProtocol

logger = logging.getLogger(__name__)

_weave_client: Optional[WeaveClientProtocol] = None


def init_tracer(client: WeaveClientProtocol) -> None:
    global _weave_client
    _weave_client = client


def traced(name: str, metadata_fn: Optional[Callable] = None):
    """
    Decorator that wraps a function with a Weave trace span.

    metadata_fn receives the same *args/**kwargs as the decorated function
    and returns a dict of metadata to attach to the span.

    Example:
        @traced("cortex_call", metadata_fn=lambda self, user, **_: {"user_id": user.user_id})
        def call_agent(self, user, question): ...
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if _weave_client is None:
                return fn(*args, **kwargs)
            metadata = metadata_fn(*args, **kwargs) if metadata_fn else {}
            ctx = _weave_client.start_trace(name, metadata)
            try:
                result = fn(*args, **kwargs)
                _weave_client.end_trace(ctx, status="ok")
                return result
            except Exception as exc:
                _weave_client.log_event(ctx, "error", {
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                })
                _weave_client.end_trace(ctx, status="error")
                raise
        return wrapper
    return decorator
