"""Configuration for the InstaInstru MCP server."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment."""

    api_base_url: str = "https://api.instainstru.com"
    api_service_token: str
    workos_domain: str | None = None
    workos_client_id: str | None = None
    workos_client_secret: str | None = None

    jwt_private_key: str | None = None
    jwt_public_key: str | None = None
    jwt_key_id: str = "mcp-key-1"
    oauth_issuer: str | None = None

    model_config = SettingsConfigDict(env_prefix="INSTAINSTRU_MCP_", env_file=".env")
