"""Audit log tools for governance and debugging."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient
from .common import format_rfc3339, resolve_time_window


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_audit_search(
        actor_email: str | None = None,
        actor_id: str | None = None,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        status: str | None = None,
        since_hours: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Search audit logs across actors, actions, and resources."""
        start_dt, end_dt, source_label = resolve_time_window(
            since_hours=since_hours,
            start_time=start_time,
            end_time=end_time,
            default_hours=24,
        )
        response = await client.audit_search(
            actor_email=actor_email,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            start_time=format_rfc3339(start_dt),
            end_time=format_rfc3339(end_dt),
            limit=limit,
        )
        meta = response.get("meta", {})
        time_window = meta.get("time_window", {})
        time_window.update(
            {
                "start": format_rfc3339(start_dt),
                "end": format_rfc3339(end_dt),
                "source": source_label,
            }
        )
        meta["time_window"] = time_window
        response["meta"] = meta
        return response

    async def instainstru_audit_user_activity(
        user_email: str,
        since_days: int = 30,
        since_hours: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Get audit activity for a specific user email."""
        effective_hours = since_hours if since_hours is not None else since_days * 24
        start_dt, end_dt, source_label = resolve_time_window(
            since_hours=effective_hours,
            start_time=start_time,
            end_time=end_time,
            default_hours=effective_hours,
        )
        response = await client.audit_user_activity(
            user_email=user_email,
            since_days=since_days,
            since_hours=effective_hours,
            start_time=format_rfc3339(start_dt),
            end_time=format_rfc3339(end_dt),
            limit=limit,
        )
        meta = response.get("meta", {})
        time_window = meta.get("time_window", {})
        time_window.update(
            {
                "start": format_rfc3339(start_dt),
                "end": format_rfc3339(end_dt),
                "source": source_label,
            }
        )
        meta["time_window"] = time_window
        response["meta"] = meta
        return response

    async def instainstru_audit_resource_history(
        resource_type: str,
        resource_id: str,
        since_hours: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 50,
    ) -> dict:
        """Get audit history for a specific resource."""
        start_dt, end_dt, source_label = resolve_time_window(
            since_hours=since_hours,
            start_time=start_time,
            end_time=end_time,
            default_hours=24,
        )
        response = await client.audit_resource_history(
            resource_type=resource_type,
            resource_id=resource_id,
            start_time=format_rfc3339(start_dt),
            end_time=format_rfc3339(end_dt),
            limit=limit,
        )
        meta = response.get("meta", {})
        time_window = meta.get("time_window", {})
        time_window.update(
            {
                "start": format_rfc3339(start_dt),
                "end": format_rfc3339(end_dt),
                "source": source_label,
            }
        )
        meta["time_window"] = time_window
        response["meta"] = meta
        return response

    async def instainstru_audit_recent_admin_actions(
        since_hours: int | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Get recent admin/MCP actions."""
        start_dt, end_dt, source_label = resolve_time_window(
            since_hours=since_hours,
            start_time=start_time,
            end_time=end_time,
            default_hours=24,
        )
        response = await client.audit_recent_admin_actions(
            start_time=format_rfc3339(start_dt),
            end_time=format_rfc3339(end_dt),
            limit=limit,
        )
        meta = response.get("meta", {})
        time_window = meta.get("time_window", {})
        time_window.update(
            {
                "start": format_rfc3339(start_dt),
                "end": format_rfc3339(end_dt),
                "source": source_label,
            }
        )
        meta["time_window"] = time_window
        response["meta"] = meta
        return response

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
