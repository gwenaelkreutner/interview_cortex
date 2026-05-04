from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SNOWFLAKE_ACCOUNT: str = "account.snowflakecomputing.com"
    SNOWFLAKE_USER: str = "user"
    SNOWFLAKE_PASSWORD: str = "password"
    SNOWFLAKE_DATABASE: str = "DB"
    SNOWFLAKE_SCHEMA: str = "PUBLIC"
    SNOWFLAKE_WAREHOUSE: str = "COMPUTE_WH"

    CORTEX_AGENT_BASE_URL: str = "https://cortex.example.com"
    CORTEX_AGENT_API_KEY: str = "secret"

    EMAIL_PROVIDER: str = "stub"
    EMAIL_FROM_ADDRESS: str = "insights@example.com"

    WEAVE_PROJECT_NAME: str = "cortex-insights"

    MAX_RETRIES: int = 3
    BATCH_CONCURRENCY: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
