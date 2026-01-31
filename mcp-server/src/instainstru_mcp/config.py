"""Configuration for the InstaInstru MCP server."""

from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment."""

    api_base_url: str = "https://api.instainstru.com"
    api_service_token: SecretStr = SecretStr("")
    grafana_cloud_url: str = ""
    grafana_cloud_api_key: SecretStr = SecretStr("")
    grafana_prometheus_datasource_uid: str = "prometheus"
    sentry_dsn: str | None = None
    sentry_api_token: SecretStr = Field(
        default=SecretStr(""), alias="INSTAINSTRU_MCP_SENTRY_API_TOKEN"
    )
    sentry_org: str = Field(default="instainstru", alias="INSTAINSTRU_MCP_SENTRY_ORG")
    environment: str = "development"
    workos_domain: str | None = None
    workos_client_id: str | None = None
    workos_client_secret: str | None = None
    workos_m2m_client_id: str = ""
    workos_m2m_client_secret: SecretStr = SecretStr("")
    workos_m2m_token_url: str = "https://api.workos.com/oauth/token"
    workos_m2m_audience: str = "https://api.instainstru.com"

    jwt_private_key: str | None = None
    jwt_public_key: str | None = None
    jwt_key_id: str = "mcp-key-1"
    oauth_issuer: str | None = None

    model_config = SettingsConfigDict(env_prefix="INSTAINSTRU_MCP_", env_file=".env")
