import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from enum import Enum

from clients.base import EmailClientProtocol, EmailDeliveryError, WeaveClientProtocol
from models.delivery import DeliveryStatus
from models.insight import InsightRun
from repositories.delivery_repository import DeliveryRepository
from repositories.insight_repository import InsightRepository
from repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class DeliveryResultKind(str, Enum):
    SENT = "sent"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class DeliveryResult:
    kind: DeliveryResultKind
    run_id: str
    user_id: str
    delivery_id: str | None = None
    error: str | None = None


@dataclass
class DeliveryBatchSummary:
    batch_date: date
    total: int
    sent: int
    skipped: int
    failed: int

    def __str__(self) -> str:
        return (
            f"DeliveryBatchSummary[{self.batch_date}] "
            f"total={self.total} sent={self.sent} "
            f"skipped={self.skipped} failed={self.failed}"
        )


class DeliveryService:
    def __init__(
        self,
        insight_repo: InsightRepository,
        delivery_repo: DeliveryRepository,
        user_repo: UserRepository,
        email_client: EmailClientProtocol,
        weave_client: WeaveClientProtocol,
        max_retries: int = 3,
        batch_concurrency: int = 5,
    ):
        self._insight_repo = insight_repo
        self._delivery_repo = delivery_repo
        self._user_repo = user_repo
        self._email = email_client
        self._weave = weave_client
        self._max_retries = max_retries
        self._batch_concurrency = batch_concurrency

    def run_batch(self, batch_date: date) -> DeliveryBatchSummary:
        pending_runs = self._insight_repo.get_completed_without_delivery(batch_date)
        logger.info(
            f"Starting delivery batch for {batch_date} with {len(pending_runs)} pending runs"
        )

        batch_ctx = self._weave.start_trace(
            "delivery_batch",
            {"batch_date": str(batch_date), "total_runs": len(pending_runs)},
        )
        results: list[DeliveryResult] = []

        with ThreadPoolExecutor(max_workers=self._batch_concurrency) as pool:
            futures = {pool.submit(self._deliver_insight, run): run for run in pending_runs}
            for future in as_completed(futures):
                results.append(future.result())

        summary = DeliveryBatchSummary(
            batch_date=batch_date,
            total=len(pending_runs),
            sent=sum(1 for r in results if r.kind == DeliveryResultKind.SENT),
            skipped=sum(1 for r in results if r.kind == DeliveryResultKind.SKIPPED),
            failed=sum(1 for r in results if r.kind == DeliveryResultKind.FAILED),
        )
        self._weave.end_trace(
            batch_ctx,
            status="ok",
            result_metadata={"sent": summary.sent, "failed": summary.failed},
        )
        logger.info(str(summary))
        return summary

    def _deliver_insight(self, run: InsightRun) -> DeliveryResult:
        try:
            return self._run_delivery_for_run(run)
        except Exception as exc:
            logger.exception(f"Unexpected error delivering run={run.run_id}")
            return DeliveryResult(
                kind=DeliveryResultKind.FAILED,
                run_id=run.run_id,
                user_id=run.user_id,
                error=str(exc),
            )

    def _run_delivery_for_run(self, run: InsightRun) -> DeliveryResult:
        user = self._user_repo.get_user_by_id(run.user_id)
        if user is None:
            return DeliveryResult(
                kind=DeliveryResultKind.FAILED,
                run_id=run.run_id,
                user_id=run.user_id,
                error=f"User {run.user_id} not found",
            )

        record, _ = self._delivery_repo.get_or_create_delivery(
            run_id=run.run_id,
            user_id=user.user_id,
            recipient_email=user.email,
        )

        if record.status == DeliveryStatus.SENT:
            logger.debug(f"run={run.run_id}: already SENT — skipping")
            return DeliveryResult(
                kind=DeliveryResultKind.SKIPPED,
                run_id=run.run_id,
                user_id=user.user_id,
                delivery_id=record.delivery_id,
            )

        if record.status == DeliveryStatus.FAILED and not record.is_retryable(self._max_retries):
            logger.warning(f"run={run.run_id}: max retries reached — skipping")
            return DeliveryResult(
                kind=DeliveryResultKind.SKIPPED,
                run_id=run.run_id,
                user_id=user.user_id,
                delivery_id=record.delivery_id,
            )

        self._delivery_repo.increment_attempt(record.delivery_id)

        trace_ctx = self._weave.start_trace(
            "user_delivery",
            {
                "user_id": user.user_id,
                "run_id": run.run_id,
                "delivery_id": record.delivery_id,
                "parent_inference_trace_id": run.weave_trace_id,
                "attempt": record.attempt_count + 1,
            },
        )

        try:
            body_html, body_text = self._render_email(user.full_name, run.ai_response or "")
            receipt = self._email.send(
                to=user.email,
                subject="Your Weekly Insight",
                body_html=body_html,
                body_text=body_text,
            )
            self._delivery_repo.mark_sent(record.delivery_id, receipt.message_id)
            self._weave.end_trace(
                trace_ctx,
                status="ok",
                result_metadata={"message_id": receipt.message_id},
            )
            logger.info(f"run={run.run_id} user={user.user_id}: email SENT")
            return DeliveryResult(
                kind=DeliveryResultKind.SENT,
                run_id=run.run_id,
                user_id=user.user_id,
                delivery_id=record.delivery_id,
            )

        except EmailDeliveryError as exc:
            error_message = str(exc)
            self._delivery_repo.mark_failed(record.delivery_id, error_message)
            self._weave.log_event(trace_ctx, "email_error", {
                "error": error_message, "user_id": user.user_id,
            })
            self._weave.end_trace(trace_ctx, status="error")
            logger.error(f"run={run.run_id} user={user.user_id}: delivery FAILED — {error_message}")
            return DeliveryResult(
                kind=DeliveryResultKind.FAILED,
                run_id=run.run_id,
                user_id=user.user_id,
                delivery_id=record.delivery_id,
                error=error_message,
            )

    @staticmethod
    def _render_email(full_name: str, ai_response: str) -> tuple[str, str]:
        body_text = (
            f"Hello {full_name},\n\n"
            f"Here is your weekly insight:\n\n{ai_response}\n\n"
            f"Best regards,\nThe Cortex Team"
        )
        body_html = (
            f"<html><body>"
            f"<p>Hello {full_name},</p>"
            f"<p>Here is your weekly insight:</p>"
            f"<blockquote>{ai_response}</blockquote>"
            f"<p>Best regards,<br>The Cortex Team</p>"
            f"</body></html>"
        )
        return body_html, body_text
