"""Configuration for the InstaInstru MCP server."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment."""

    api_base_url: str = "https://api.instainstru.com"
    api_service_token: str

    model_config = SettingsConfigDict(env_prefix="INSTAINSTRU_MCP_", env_file=".env")
