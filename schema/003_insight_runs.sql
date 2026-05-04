CREATE TABLE IF NOT EXISTS insight_runs (
    run_id          VARCHAR(64)  NOT NULL PRIMARY KEY,
    batch_date      DATE         NOT NULL,
    user_id         VARCHAR(64)  NOT NULL REFERENCES users(user_id),
    question        TEXT         NOT NULL,
    ai_response     TEXT,
    status          VARCHAR(32)  NOT NULL DEFAULT 'PENDING',
    -- PENDING | IN_PROGRESS | COMPLETED | FAILED
    error_message   TEXT,
    cortex_trace_id VARCHAR(256),
    weave_trace_id  VARCHAR(256),
    attempt_count   INTEGER      NOT NULL DEFAULT 0,
    created_at      TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_at      TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_insight_runs_user_date
    ON insight_runs (user_id, batch_date);

CREATE INDEX IF NOT EXISTS idx_insight_runs_batch_date_status
    ON insight_runs (batch_date, status);
