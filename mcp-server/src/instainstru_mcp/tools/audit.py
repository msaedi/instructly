"""Audit log tools for governance and debugging."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_audit_search(
        actor_email: str | None = None,
        actor_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        status: str | None = None,
        since_hours: int = 24,
        limit: int = 100,
    ) -> dict:
        """Search audit logs across actors, actions, and resources."""
        return await client.audit_search(
            actor_email=actor_email,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            since_hours=since_hours,
            limit=limit,
        )

    async def instainstru_audit_user_activity(
        user_email: str,
        since_days: int = 30,
        limit: int = 100,
    ) -> dict:
        """Get audit activity for a specific user email."""
        return await client.audit_user_activity(
            user_email=user_email,
            since_days=since_days,
            limit=limit,
        )

    async def instainstru_audit_resource_history(
        resource_type: str,
        resource_id: str,
        limit: int = 50,
    ) -> dict:
        """Get audit history for a specific resource."""
        return await client.audit_resource_history(
            resource_type=resource_type,
            resource_id=resource_id,
            limit=limit,
        )

    async def instainstru_audit_recent_admin_actions(
        since_hours: int = 24,
        limit: int = 100,
    ) -> dict:
        """Get recent admin/MCP actions."""
        return await client.audit_recent_admin_actions(
            since_hours=since_hours,
            limit=limit,
        )

    mcp.tool()(instainstru_audit_search)
    mcp.tool()(instainstru_audit_user_activity)
    mcp.tool()(instainstru_audit_resource_history)
    mcp.tool()(instainstru_audit_recent_admin_actions)

    return {
        "instainstru_audit_search": instainstru_audit_search,
        "instainstru_audit_user_activity": instainstru_audit_user_activity,
        "instainstru_audit_resource_history": instainstru_audit_resource_history,
        "instainstru_audit_recent_admin_actions": instainstru_audit_recent_admin_actions,
    }
