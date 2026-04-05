from __future__ import annotations

from pydantic import Field, SecretStr, field_validator

from .shared import secret_or_plain


class OperationsSettingsMixin:
    redis_url: SecretStr = Field(default=SecretStr("redis://localhost:6379"))
    cache_ttl: int = 3600
    scheduler_enabled: bool = Field(
        default=True,
        description="Enable background schedulers (disabled automatically during tests)",
    )
    jobs_backoff_base: int = Field(
        default=30,
        description="Base backoff in seconds for background job retries",
        ge=1,
    )
    jobs_backoff_cap: int = Field(
        default=1800,
        description="Maximum backoff in seconds for background job retries",
        ge=1,
    )
    jobs_poll_interval: int = Field(
        default=2,
        description="Background job worker poll interval in seconds",
        ge=1,
    )
    jobs_batch: int = Field(
        default=25,
        description="Maximum number of jobs processed per polling interval",
        ge=1,
    )
    jobs_max_attempts: int = Field(
        default=5,
        description="Maximum retry attempts before moving a job to the dead-letter queue",
        ge=1,
    )
    metrics_ip_allowlist: list[str] = Field(
        default_factory=list,
        description="Comma-separated IPs/CIDRs allowed for /internal/metrics (when non-empty)",
    )
    metrics_max_bytes: int = Field(
        default=8_000_000,
        description="Cap response size for metrics",
        ge=1,
    )
    metrics_rate_limit_per_min: int = Field(
        default=6,
        description="Per-IP requests/minute for /internal/metrics",
        ge=1,
    )
    metrics_basic_auth_user: SecretStr | None = Field(
        default=None,
        description="Optional username for protecting /metrics",
    )
    metrics_basic_auth_pass: SecretStr | None = Field(
        default=None,
        description="Optional password for protecting /metrics",
    )
    template_cache_enabled: bool = Field(
        default=True,
        description="Enable template service caching (disable for development if needed)",
    )
    prometheus_http_url: str = Field(
        default="", description="Prometheus base URL, e.g., http://localhost:9090"
    )
    prometheus_bearer_token: SecretStr = Field(
        default=SecretStr(""), description="Optional bearer token for Prometheus API"
    )
    flower_url: str = Field(
        default="http://localhost:5555",
        alias="FLOWER_URL",
        description="Flower monitoring URL",
    )
    flower_basic_auth: SecretStr | None = Field(
        default=None,
        alias="FLOWER_BASIC_AUTH",
        description="Flower HTTP Basic Auth in format 'username:password'",
    )

    @field_validator("metrics_ip_allowlist", mode="before")
    @classmethod
    def _parse_metrics_ip_allowlist(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [token.strip() for token in value.split(",") if token.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(token).strip() for token in value if str(token).strip()]
        raise ValueError("metrics_ip_allowlist must be a comma-separated string or list")

    @property
    def flower_user(self) -> str | None:
        auth_value = secret_or_plain(self.flower_basic_auth).strip()
        if auth_value and ":" in auth_value:
            return auth_value.split(":", 1)[0]
        return None

    @property
    def flower_password(self) -> str | None:
        auth_value = secret_or_plain(self.flower_basic_auth).strip()
        if auth_value and ":" in auth_value:
            return auth_value.split(":", 1)[1]
        return None
