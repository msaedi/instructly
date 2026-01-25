"""FastMCP server entry point for InstaInstru admin tools."""

from __future__ import annotations

import os

from typing import Any, cast

from fastmcp import FastMCP

from .auth import MCPAuth
from .client import InstaInstruClient
from .config import Settings
from .tools import founding, instructors, invites, metrics, search


def create_mcp(
    settings: Settings | None = None,
    auth: MCPAuth | None = None,
    client: InstaInstruClient | None = None,
) -> FastMCP:
    settings = settings or Settings()  # type: ignore[call-arg]
    auth = auth or MCPAuth(settings)
    client = client or InstaInstruClient(settings, auth)

    mcp = FastMCP("InstaInstru Admin")

    founding.register_tools(mcp, client)
    instructors.register_tools(mcp, client)
    invites.register_tools(mcp, client)
    search.register_tools(mcp, client)
    metrics.register_tools(mcp, client)

    return mcp


def create_app(settings: Settings | None = None):
    mcp = create_mcp(settings=settings)
    return cast(Any, mcp).http_app(transport="sse")


mcp = create_mcp()
app = cast(Any, mcp).http_app(transport="sse")


def main() -> None:
    import uvicorn

    port = int(os.getenv("PORT", "8001"))
    uvicorn.run("instainstru_mcp.server:app", host="0.0.0.0", port=port)
