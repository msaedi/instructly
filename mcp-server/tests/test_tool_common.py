from __future__ import annotations

import inspect

import pytest
from fastmcp import FastMCP
from instainstru_mcp.client import BackendNotFoundError
from instainstru_mcp.tools.common import register_backend_tool


def test_register_backend_tool_preserves_metadata_and_signature():
    async def sample_tool(identifier: str, limit: int = 10) -> dict:
        """Look up a user."""
        return {"ok": True}

    wrapped = register_backend_tool(FastMCP("test"), sample_tool)

    assert wrapped.__name__ == "sample_tool"
    assert wrapped.__doc__ == "Look up a user."
    signature = inspect.signature(wrapped)
    assert list(signature.parameters) == ["identifier", "limit"]
    assert signature.parameters["limit"].default == 10


@pytest.mark.asyncio
async def test_register_backend_tool_read_mode_translates_not_found():
    async def sample_tool(identifier: str, limit: int = 10) -> dict:
        raise BackendNotFoundError("backend_not_found")

    wrapped = register_backend_tool(
        FastMCP("test"),
        sample_tool,
        error="user_not_found",
        message="User not found.",
        extra={"user": None},
    )

    result = await wrapped("user@example.com", limit=5)

    assert result == {
        "found": False,
        "error": "user_not_found",
        "message": "User not found.",
        "user": None,
    }


@pytest.mark.asyncio
async def test_register_backend_tool_write_mode_translates_not_found():
    async def sample_action(confirm_token: str) -> dict:
        raise BackendNotFoundError("backend_not_found")

    wrapped = register_backend_tool(
        FastMCP("test"),
        sample_action,
        mode="write",
        error="resource_not_found",
        message="Requested resource was not found.",
    )

    result = await wrapped("ctok_123")

    assert result == {
        "success": False,
        "error": "resource_not_found",
        "message": "Requested resource was not found.",
    }
