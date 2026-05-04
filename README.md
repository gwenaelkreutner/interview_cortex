# Interview Cortex

Daily batch system that generates AI-powered insights and emails them to users every Monday.
Split into two jobs: one runs inference in the morning, one sends emails later in the day.

---

## How it works

```
INFERENCE JOB  (AM)

  Snowflake[users]  ──►  resolve_question(brand, persona)
                                  │
                    ThreadPoolExecutor  (N workers)
                                  │
                       CortexAgent.call(context, question)
                                  │
  Snowflake[insight_runs] ◄── save_completed / save_failed
  Weave ◄── trace per user


DELIVERY JOB  (PM)

  Snowflake[insight_runs WHERE status=COMPLETED, not sent]
                                  │
                    ThreadPoolExecutor  (N workers)
                                  │
                             EmailClient.send(...)
                                  │
  Snowflake[delivery_records] ◄── mark_sent / mark_failed
  Weave ◄── trace linked to inference span
```

---

## Project structure

| Layer | Directory | What it does |
|---|---|---|
| Entry points | `jobs/` | Wire everything up, parse `--date`, set exit code |
| Orchestration | `services/` | Fan-out logic, error isolation, Weave tracing |
| Data access | `repositories/` | SQL queries, idempotency via `MERGE INTO` |
| Domain | `models/` | `User`, `BrandPersonaMapping`, `InsightRun`, `DeliveryRecord` |
| Clients | `clients/` | Protocol interfaces + stub implementations |
| Observability | `observability/` | `@traced` decorator |
| Config | `config/` | pydantic-settings from `.env` |
| Schema | `schema/` | Snowflake DDL |

### Snowflake tables

| Table | Purpose |
|---|---|
| `users` | Active users with `brand`, `persona`, `email` |
| `brand_persona_mappings` | `(brand, persona)` → `question_template` |
| `insight_runs` | Per-user AI result, keyed on `(user_id, batch_date)` |
| `delivery_records` | Per-run email delivery status, keyed on `run_id` |

---

## Usage

```bash
pip install -e .

cp .env.example .env
# fill in your credentials

python -m jobs.run_inference --date 2026-04-28
python -m jobs.run_delivery --date 2026-04-28

# re-running is safe — COMPLETED rows are skipped
```

Exit `0` = all good. Exit `1` = at least one user failed, retry.

---

## Design decisions

**Two jobs instead of one** — inference and delivery fail independently. An email outage shouldn't force re-running Cortex calls, and vice versa.

**`MERGE INTO` for idempotency** — no duplicate rows even if the job runs twice. Each job skips users already `COMPLETED` or `SENT`.

**`batch_date` as the idempotency key** — re-running any time on the same date is safe. Backfilling works with `--date`.

**No in-process retries** — that's the scheduler's job. `attempt_count` tracks how many times a row was attempted, capped at `MAX_RETRIES`.

**`ThreadPoolExecutor` over asyncio** — all clients are synchronous, no reason to add async complexity.

**`Protocol` interfaces** — no inheritance needed for mocks or new implementations. `MagicMock(spec=CortexClientProtocol)` just works.

**Per-user failure isolation** — one user failing doesn't stop the batch. Error details go to `insight_runs.error_message` and Weave.

---

## Observability

```
inference_batch  [batch_date, total_users]
└── user_inference  [user_id, brand, persona, run_id, attempt]

delivery_batch   [batch_date, total_runs]
└── user_delivery  [user_id, run_id, delivery_id, parent_inference_trace_id, attempt]
```

`weave_trace_id` is stored in `insight_runs` and attached to the delivery span, so you can trace end-to-end across both jobs in the Weave UI.

---

## Files

```
interview_cortex/
├── config/
│   └── settings.py
├── clients/
│   ├── base.py                  # Protocol interfaces
│   ├── snowflake_client.py
│   ├── cortex_client.py
│   ├── email_client.py
│   └── weave_client.py
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
│   ├── insight_service.py
│   └── delivery_service.py
├── jobs/
│   ├── run_inference.py
│   └── run_delivery.py
├── observability/
│   └── tracing.py
└── schema/
    ├── 001_users.sql
    ├── 002_brand_persona_mappings.sql
    ├── 003_insight_runs.sql
    └── 004_delivery_records.sql
```
