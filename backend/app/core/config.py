"""Application configuration loaded strictly from environment variables.

Fails fast at startup if a required variable is missing or malformed - never
falls back to a hardcoded secret or credential.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = Field(alias="ENVIRONMENT")

    database_url: str = Field(alias="DATABASE_URL")
    test_database_url: str = Field(alias="TEST_DATABASE_URL")

    jwt_secret_key: str = Field(alias="JWT_SECRET_KEY", min_length=32)
    jwt_algorithm: str = Field(alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(alias="ACCESS_TOKEN_EXPIRE_MINUTES", gt=0)
    refresh_token_expire_days: int = Field(alias="REFRESH_TOKEN_EXPIRE_DAYS", gt=0)

    cors_origins: str = Field(alias="CORS_ORIGINS")

    login_rate_limit: str = Field(alias="LOGIN_RATE_LIMIT")
    register_rate_limit: str = Field(alias="REGISTER_RATE_LIMIT")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
