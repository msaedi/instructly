"""Authentication helpers for MCP server requests."""

from __future__ import annotations

from .config import Settings


class AuthenticationError(Exception):
    """Raised when MCP server auth configuration is invalid."""


class MCPAuth:
    """Builds backend auth headers using a single service token."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_headers(self, request_id: str) -> dict:
        token = self.settings.api_service_token.strip()
        if not token:
            raise AuthenticationError("api_service_token_missing")
        return {
            "Authorization": f"Bearer {token}",
            "X-Request-Id": request_id,
        }
