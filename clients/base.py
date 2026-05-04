from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class CortexResponse:
    response_text: str
    trace_id: str
    tokens_used: int


@dataclass
class EmailReceipt:
    message_id: str
    accepted: bool


@dataclass
class TraceContext:
    trace_id: str
    name: str
    metadata: dict


class CortexCallError(Exception):
    pass


class EmailDeliveryError(Exception):
    pass


@runtime_checkable
class SnowflakeClientProtocol(Protocol):
    def execute_query(self, sql: str, params: dict | None = None) -> list[dict]: ...
    def execute_many(self, sql: str, rows: list[dict]) -> None: ...
    def close(self) -> None: ...


@runtime_checkable
class CortexClientProtocol(Protocol):
    def call_agent(self, user_context: dict, question: str) -> CortexResponse: ...


@runtime_checkable
class EmailClientProtocol(Protocol):
    def send(self, to: str, subject: str, body_html: str, body_text: str) -> EmailReceipt: ...


@runtime_checkable
class WeaveClientProtocol(Protocol):
    def start_trace(self, name: str, metadata: dict) -> TraceContext: ...
    def end_trace(self, ctx: TraceContext, status: str, result_metadata: dict | None = None) -> None: ...
    def log_event(self, ctx: TraceContext, event: str, data: dict) -> None: ...
