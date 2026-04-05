from __future__ import annotations

from pydantic import AliasChoices, Field, SecretStr

from .shared import (
    _default_int_database_url,
    _default_production_database_indicators,
    secret_or_plain,
)


class DatabaseSettingsMixin:
    prod_database_url_raw: SecretStr | None = Field(default=None, alias="prod_database_url")
    preview_database_url_raw: SecretStr = Field(default=SecretStr(""), alias="preview_database_url")
    int_database_url_raw: SecretStr = Field(
        default_factory=_default_int_database_url,
        alias="test_database_url",
    )
    stg_database_url_raw: SecretStr = Field(default=SecretStr(""), alias="stg_database_url")
    db_api_pool_size: int = Field(default=8, alias="DB_API_POOL_SIZE", ge=1)
    db_api_max_overflow: int = Field(default=8, alias="DB_API_MAX_OVERFLOW", ge=0)
    db_api_pool_timeout: int = Field(default=5, alias="DB_API_POOL_TIMEOUT", ge=1)
    db_worker_pool_size: int = Field(default=4, alias="DB_WORKER_POOL_SIZE", ge=1)
    db_worker_max_overflow: int = Field(default=4, alias="DB_WORKER_MAX_OVERFLOW", ge=0)
    db_worker_pool_timeout: int = Field(default=10, alias="DB_WORKER_POOL_TIMEOUT", ge=1)
    db_scheduler_pool_size: int = Field(default=4, alias="DB_SCHEDULER_POOL_SIZE", ge=1)
    db_scheduler_max_overflow: int = Field(default=4, alias="DB_SCHEDULER_MAX_OVERFLOW", ge=0)
    db_scheduler_pool_timeout: int = Field(default=10, alias="DB_SCHEDULER_POOL_TIMEOUT", ge=1)
    service_role: str = Field(
        default="api",
        alias="SERVICE_ROLE",
        validation_alias=AliasChoices("SERVICE_ROLE", "DB_POOL_ROLE"),
        description="Service role for pool monitoring (api, worker, scheduler, all)",
    )
    production_database_indicators: list[str] = Field(
        default_factory=_default_production_database_indicators
    )

    def get_database_url(self) -> str:
        """Get the appropriate database URL based on context."""

        from ..database_config import DatabaseConfig

        db_config = DatabaseConfig()
        return db_config.get_database_url()

    def is_production_database(self, url: str | None = None) -> bool:
        """Check if a database URL appears to be a production database."""

        check_url = url or secret_or_plain(self.prod_database_url_raw)
        return any(
            indicator in check_url.lower() for indicator in self.production_database_indicators
        )

    @property
    def database_url(self) -> str:
        """SAFE database URL property resolved via DatabaseConfig and SITE_MODE."""

        from ..database_config import DatabaseConfig

        db_config = DatabaseConfig()
        return db_config.get_database_url()

    @property
    def test_database_url(self) -> str:
        """Backward compatibility - always returns INT database."""

        return secret_or_plain(self.int_database_url_raw)

    @property
    def stg_database_url(self) -> str:
        """Staging database URL."""

        return secret_or_plain(self.stg_database_url_raw)
