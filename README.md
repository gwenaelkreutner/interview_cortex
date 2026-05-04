# Interview Cortex — Daily Batch Insight System

A daily scheduled batch workflow that generates and delivers personalized AI-powered insights to users every Monday. The system is split into two independently runnable jobs to maximize reliability and separation of concerns.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    INFERENCE JOB  (AM)                       │
│                                                              │
│  Snowflake[users]  ──►  resolve_question(brand, persona)     │
│                                  │                           │
│                                  ▼                           │
│              ThreadPoolExecutor  (N workers)                 │
│                                  │                           │
│                     CortexAgent.call(context, question)      │
│                                  │                           │
│  Snowflake[insight_runs] ◄── save_completed / save_failed    │
│                                                              │
│  Weave ◄── traces per user  (user_id, brand, persona, ...)   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    DELIVERY JOB  (PM)                        │
│                                                              │
│  Snowflake[insight_runs WHERE status=COMPLETED, not sent]    │
│                                  │                           │
│              ThreadPoolExecutor  (N workers)                 │
│                                  │                           │
│                         EmailClient.send(...)                │
│                                  │                           │
│  Snowflake[delivery_records] ◄── mark_sent / mark_failed     │
│                                                              │
│  Weave ◄── traces cross-linked to inference span            │
└─────────────────────────────────────────────────────────────┘
```

---

## Architecture

### Layers

| Layer | Directory | Responsibility |
|---|---|---|
| Entry points | `jobs/` | Wire clients & services, parse `--date`, set exit code |
| Orchestration | `services/` | Fan-out logic, error isolation, Weave tracing |
| Data access | `repositories/` | SQL queries, idempotency via `MERGE INTO` |
| Domain | `models/` | Dataclasses: `User`, `BrandPersonaMapping`, `InsightRun`, `DeliveryRecord` |
| Integrations | `clients/` | `Protocol` interfaces + stub implementations |
| Observability | `observability/` | `@traced` decorator, Weave helpers |
| Configuration | `config/` | `pydantic-settings` from environment / `.env` |
| Schema | `schema/` | Snowflake DDL |

### Snowflake Tables

| Table | Purpose |
|---|---|
| `users` | Active users with `brand`, `persona`, `email` |
| `brand_persona_mappings` | `(brand, persona)` → `question_template` |
| `insight_runs` | Per-user AI result, keyed on `(user_id, batch_date)` |
| `delivery_records` | Per-run email delivery status, keyed on `run_id` |

---

## Usage

```bash
# Install
pip install -e .

# Configure
cp .env.example .env
# edit .env with your real credentials

# Run inference job (morning)
python -m jobs.run_inference --date 2026-04-28

# Run delivery job (later in the day)
python -m jobs.run_delivery --date 2026-04-28

# Re-running for the same date is safe — COMPLETED rows are skipped
python -m jobs.run_inference --date 2026-04-28
```

Exit code `0` = all users processed without failure. Exit code `1` = at least one user failed (scheduler should retry).

---

## Key Design Decisions

### 1. Two independent jobs instead of one monolithic pipeline

The inference (AI) and email delivery steps have different SLAs, different failure modes, and different retry costs. Splitting them means:
- An email provider outage does not require re-running expensive Cortex calls.
- A Cortex outage does not delay emails for already-completed runs.
- Both jobs accept `--date`, enabling independent retries and backfilling for any past date.

**Trade-off**: Two scheduled tasks to operate instead of one. Mitigated by the shared `--date` argument and clear exit codes.

### 2. Idempotency via `MERGE INTO`, not application-level check-then-insert

`insight_runs` and `delivery_records` are created using Snowflake's atomic `MERGE INTO`, keyed on `(user_id, batch_date)` and `run_id` respectively. This prevents duplicate rows even if the job is accidentally triggered twice concurrently (TOCTOU-safe). On re-run, each job inspects the current row status and skips users that are already `COMPLETED` or `SENT`.

**Trade-off**: `MERGE` is slightly more complex than `INSERT OR IGNORE`. The repository layer encapsulates this, so services never see raw SQL.

### 3. `batch_date` as the logical idempotency key

Using a `DATE` (not a wall-clock timestamp) means a re-run at any point during the day for the same logical date is safe. Historical dates can be backfilled with `--date 2026-01-06`.

**Trade-off**: One insight per user per day, by design.

### 4. No in-process retry loops

Retry timing belongs to the scheduler (Airflow, cron with wrapper, GitHub Actions). The `attempt_count` column tracks how many times each user's row has been attempted, capping at `MAX_RETRIES`. In-process `sleep`-based retries make job duration unpredictable and hide failures from the scheduler.

**Trade-off**: Requires the scheduler to be configured with retry logic. For plain cron, a simple wrapper script that re-invokes the job N times suffices.

### 5. `ThreadPoolExecutor` over asyncio

All external clients (Snowflake, Cortex, Email) are synchronous. Wrapping synchronous I/O in `asyncio` adds complexity without benefit. `ThreadPoolExecutor` with configurable `BATCH_CONCURRENCY` is straightforward and debuggable.

**Trade-off**: Thread overhead per user. For user counts beyond ~50k, the architecture would shift to a queue-based fanout (SQS / Pub-Sub + worker fleet), but the service interface does not need to change.

### 6. `Protocol` interfaces for all clients

Python structural subtyping (`Protocol`) means mock objects in tests need not inherit from a base class. `unittest.mock.MagicMock(spec=CortexClientProtocol)` works out of the box. Adding a new email provider only requires implementing the three methods — no inheritance needed.

**Trade-off**: Slightly weaker IDE auto-complete compared to ABCs in some editors. Running `mypy --strict` in CI compensates.

### 7. Per-user failure isolation

Each worker in `ThreadPoolExecutor` wraps the full user processing in `try/except`. An unhandled exception for user A returns `UserResult.failed` and lets the batch continue. Error details are persisted to `insight_runs.error_message` and emitted to Weave for post-mortem.

---

## Observability

Every job emits structured Weave traces. The hierarchy is:

```
inference_batch  [batch_date, total_users]
└── user_inference  [user_id, brand, persona, run_id, attempt]

delivery_batch   [batch_date, total_runs]
└── user_delivery  [user_id, run_id, delivery_id, parent_inference_trace_id, attempt]
```

`weave_trace_id` is stored in `insight_runs`. The delivery job reads it and attaches it as `parent_inference_trace_id` on its own span, enabling end-to-end tracing across two separate job invocations in the Weave UI.

---

## Project Structure

```
interview_cortex/
├── README.md
├── pyproject.toml
├── .env.example
├── config/
│   └── settings.py              # Pydantic BaseSettings
├── clients/
│   ├── base.py                  # Protocol interfaces + response dataclasses
│   ├── snowflake_client.py      # In-memory stub (replace with real connector)
│   ├── cortex_client.py         # Cortex Agent stub
│   ├── email_client.py          # Email stub
│   └── weave_client.py          # Weave observability stub
├── models/
│   ├── user.py
│   ├── mapping.py
│   ├── insight.py
│   └── delivery.py
├── repositories/
│   ├── user_repository.py
│   ├── mapping_repository.py
│   ├── insight_repository.py
│   └── delivery_repository.py
├── services/
│   ├── insight_service.py       # AI batch orchestration
│   └── delivery_service.py      # Email delivery orchestration
├── jobs/
│   ├── run_inference.py         # Entry point: morning AI job
│   └── run_delivery.py          # Entry point: email delivery job
├── observability/
│   └── tracing.py               # @traced decorator
└── schema/
    ├── 001_users.sql
    ├── 002_brand_persona_mappings.sql
    ├── 003_insight_runs.sql
    └── 004_delivery_records.sql
```
