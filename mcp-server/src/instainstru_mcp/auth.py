"""Authentication helpers for MCP server requests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import SecretStr

if TYPE_CHECKING:
    from .config import Settings


class AuthenticationError(Exception):
    """Raised when MCP server auth configuration is invalid."""


class MCPAuth:
    """Builds backend auth headers using a single service token."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_headers(self, request_id: str) -> dict:
        headers = {"X-Request-Id": request_id}
        token = _secret_value(self.settings.api_service_token).strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
            return headers
        if _has_m2m_config(self.settings):
            return headers
        raise AuthenticationError("api_service_token_missing")


def _secret_value(value: SecretStr | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return str(value)


def _has_m2m_config(settings: Settings) -> bool:
    return bool(
        settings.workos_m2m_client_id
        and _secret_value(settings.workos_m2m_client_secret).strip()
        and settings.workos_m2m_token_url
        and settings.workos_m2m_audience
    )
