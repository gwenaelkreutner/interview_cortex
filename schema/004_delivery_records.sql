CREATE TABLE IF NOT EXISTS delivery_records (
    delivery_id         VARCHAR(64)  NOT NULL PRIMARY KEY,
    run_id              VARCHAR(64)  NOT NULL REFERENCES insight_runs(run_id),
    user_id             VARCHAR(64)  NOT NULL,
    recipient_email     VARCHAR(256) NOT NULL,
    status              VARCHAR(32)  NOT NULL DEFAULT 'PENDING',
    -- PENDING | SENT | FAILED
    provider_message_id VARCHAR(256),
    error_message       TEXT,
    attempt_count       INTEGER      NOT NULL DEFAULT 0,
    sent_at             TIMESTAMP_TZ,
    created_at          TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    updated_at          TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_delivery_records_run_id
    ON delivery_records (run_id);

CREATE INDEX IF NOT EXISTS idx_delivery_records_status
    ON delivery_records (status);
