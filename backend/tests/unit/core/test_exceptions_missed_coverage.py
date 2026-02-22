"""Tests targeting missed lines in app/core/exceptions.py.

Missed lines:
  67: MCPTokenError with details parameter
  122: UnauthorizedException.to_http_exception
  215: InsufficientNoticeException construction
"""
from __future__ import annotations

from app.core.exceptions import (
    InsufficientNoticeException,
    MCPTokenError,
    UnauthorizedException,
)


def test_mcp_token_error_with_details() -> None:
    """Line 67: MCPTokenError with details kwarg."""
    exc = MCPTokenError("expired", details={"token_id": "abc123"})
    assert exc.reason == "expired"
    assert exc.details["reason"] == "expired"
    assert exc.details["token_id"] == "abc123"
    assert exc.code == "MCP_TOKEN_EXPIRED"

    http_exc = exc.to_http_exception()
    assert http_exc.status_code == 400


def test_mcp_token_error_without_details() -> None:
    """MCPTokenError without details kwarg."""
    exc = MCPTokenError("invalid")
    assert exc.reason == "invalid"
    assert exc.details == {"reason": "invalid"}
    assert exc.code == "MCP_TOKEN_INVALID"


def test_unauthorized_exception_to_http() -> None:
    """Line 122: UnauthorizedException.to_http_exception."""
    exc = UnauthorizedException("Not authenticated")
    http_exc = exc.to_http_exception()
    assert http_exc.status_code == 401
    assert http_exc.detail["message"] == "Not authenticated"
    assert http_exc.detail["code"] == "UnauthorizedException"


def test_insufficient_notice_exception() -> None:
    """Line 215: InsufficientNoticeException construction."""
    exc = InsufficientNoticeException(required_hours=24, provided_hours=12.5)
    assert "24 hours" in exc.message
    assert exc.details["required_hours"] == 24
    assert exc.details["provided_hours"] == 12.5
    assert exc.code == "INSUFFICIENT_NOTICE"

    http_exc = exc.to_http_exception()
    assert http_exc.status_code == 422
