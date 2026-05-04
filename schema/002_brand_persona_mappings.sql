CREATE TABLE IF NOT EXISTS brand_persona_mappings (
    mapping_id        VARCHAR(64)   NOT NULL PRIMARY KEY,
    brand             VARCHAR(128)  NOT NULL,
    persona           VARCHAR(128)  NOT NULL,
    question_template VARCHAR(2048) NOT NULL,
    is_active         BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMP_TZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),

    UNIQUE (brand, persona)
);
