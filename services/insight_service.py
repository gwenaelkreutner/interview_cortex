import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from enum import Enum

from clients.base import CortexCallError, CortexClientProtocol, WeaveClientProtocol
from models.insight import InsightStatus
from models.user import User
from repositories.insight_repository import InsightRepository
from repositories.mapping_repository import MappingRepository
from repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class UserResultKind(str, Enum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class UserResult:
    kind: UserResultKind
    user_id: str
    run_id: str | None = None
    error: str | None = None


@dataclass
class BatchSummary:
    batch_date: date
    total: int
    completed: int
    skipped: int
    failed: int

    def __str__(self) -> str:
        return (
            f"BatchSummary[{self.batch_date}] "
            f"total={self.total} completed={self.completed} "
            f"skipped={self.skipped} failed={self.failed}"
        )


class InsightService:
    def __init__(
        self,
        user_repo: UserRepository,
        mapping_repo: MappingRepository,
        insight_repo: InsightRepository,
        cortex_client: CortexClientProtocol,
        weave_client: WeaveClientProtocol,
        max_retries: int = 3,
        batch_concurrency: int = 5,
    ):
        self._user_repo = user_repo
        self._mapping_repo = mapping_repo
        self._insight_repo = insight_repo
        self._cortex = cortex_client
        self._weave = weave_client
        self._max_retries = max_retries
        self._batch_concurrency = batch_concurrency

    def run_batch(self, batch_date: date) -> BatchSummary:
        users = self._user_repo.load_active_users()
        logger.info(f"Starting inference batch for {batch_date} with {len(users)} active users")

        batch_ctx = self._weave.start_trace(
            "inference_batch",
            {"batch_date": str(batch_date), "total_users": len(users)},
        )
        results: list[UserResult] = []

        with ThreadPoolExecutor(max_workers=self._batch_concurrency) as pool:
            futures = {pool.submit(self._process_user, user, batch_date): user for user in users}
            for future in as_completed(futures):
                results.append(future.result())

        summary = BatchSummary(
            batch_date=batch_date,
            total=len(users),
            completed=sum(1 for r in results if r.kind == UserResultKind.COMPLETED),
            skipped=sum(1 for r in results if r.kind == UserResultKind.SKIPPED),
            failed=sum(1 for r in results if r.kind == UserResultKind.FAILED),
        )
        self._weave.end_trace(
            batch_ctx,
            status="ok",
            result_metadata={"completed": summary.completed, "failed": summary.failed},
        )
        logger.info(str(summary))
        return summary

    def _process_user(self, user: User, batch_date: date) -> UserResult:
        try:
            return self._run_inference_for_user(user, batch_date)
        except Exception as exc:
            logger.exception(f"Unexpected error processing user={user.user_id}")
            return UserResult(kind=UserResultKind.FAILED, user_id=user.user_id, error=str(exc))

    def _run_inference_for_user(self, user: User, batch_date: date) -> UserResult:
        mapping = self._mapping_repo.resolve_question(user.brand, user.persona)
        if mapping is None:
            error = f"No mapping found for brand={user.brand!r}, persona={user.persona!r}"
            logger.warning(f"user={user.user_id}: {error}")
            return UserResult(kind=UserResultKind.FAILED, user_id=user.user_id, error=error)

        question = mapping.render_question(user)
        run, _ = self._insight_repo.get_or_create_run(user.user_id, question, batch_date)

        if run.status == InsightStatus.COMPLETED:
            logger.debug(f"user={user.user_id} run={run.run_id}: already COMPLETED — skipping")
            return UserResult(kind=UserResultKind.SKIPPED, user_id=user.user_id, run_id=run.run_id)

        if run.status == InsightStatus.FAILED and not run.is_retryable(self._max_retries):
            logger.warning(f"user={user.user_id} run={run.run_id}: max retries reached — skipping")
            return UserResult(kind=UserResultKind.SKIPPED, user_id=user.user_id, run_id=run.run_id)

        self._insight_repo.mark_in_progress(run.run_id)
        self._insight_repo.increment_attempt(run.run_id)

        trace_ctx = self._weave.start_trace(
            "user_inference",
            {
                "user_id": user.user_id,
                "brand": user.brand,
                "persona": user.persona,
                "run_id": run.run_id,
                "batch_date": str(batch_date),
                "attempt": run.attempt_count + 1,
            },
        )

        try:
            response = self._cortex.call_agent(
                user_context=user.as_context(),
                question=question,
            )
            self._insight_repo.save_completed(
                run_id=run.run_id,
                ai_response=response.response_text,
                cortex_trace_id=response.trace_id,
                weave_trace_id=trace_ctx.trace_id,
            )
            self._weave.end_trace(
                trace_ctx,
                status="ok",
                result_metadata={"tokens_used": response.tokens_used},
            )
            logger.info(f"user={user.user_id} run={run.run_id}: COMPLETED")
            return UserResult(kind=UserResultKind.COMPLETED, user_id=user.user_id, run_id=run.run_id)

        except CortexCallError as exc:
            error_message = str(exc)
            self._insight_repo.save_failed(run.run_id, error_message)
            self._weave.log_event(trace_ctx, "cortex_error", {
                "error": error_message, "user_id": user.user_id,
            })
            self._weave.end_trace(trace_ctx, status="error")
            logger.error(f"user={user.user_id} run={run.run_id}: FAILED — {error_message}")
            return UserResult(
                kind=UserResultKind.FAILED,
                user_id=user.user_id,
                run_id=run.run_id,
                error=error_message,
            )
