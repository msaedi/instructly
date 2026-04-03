"""MCP tools for service catalog resolution."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient
from .common import register_backend_tool


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_services_catalog() -> dict:
        """List all services with their canonical slugs and category mappings."""
        return await client.get_services_catalog()

    async def instainstru_service_lookup(query: str) -> dict:
        """Resolve a service name or slug to its canonical form."""
        return await client.lookup_service(query)

    instainstru_services_catalog = register_backend_tool(
        mcp,
        instainstru_services_catalog,
    )
    instainstru_service_lookup = register_backend_tool(
        mcp,
        instainstru_service_lookup,
    )

    return {
        "instainstru_services_catalog": instainstru_services_catalog,
        "instainstru_service_lookup": instainstru_service_lookup,
    }
