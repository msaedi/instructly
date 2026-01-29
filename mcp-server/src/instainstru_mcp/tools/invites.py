"""MCP tools for founding instructor invites."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_invites_preview(
        recipient_emails: list[str],
        grant_founding_status: bool = True,
        expires_in_days: int = 14,
        message_note: str | None = None,
    ) -> dict:
        """Preview sending invites to prospective instructors."""
        payload = {
            "recipient_emails": recipient_emails,
            "grant_founding_status": grant_founding_status,
            "expires_in_days": expires_in_days,
            "message_note": message_note,
        }
        return await client.preview_invites(**payload)

    async def instainstru_invites_send(
        confirm_token: str,
        idempotency_key: str,
    ) -> dict:
        """Send invites after confirming preview token."""
        return await client.send_invites(confirm_token, idempotency_key)

    async def instainstru_invites_list(
        email: str | None = None,
        status: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict:
        """List invites with optional filters."""
        params = {
            "email": email,
            "status": status,
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit,
            "cursor": cursor,
        }
        return await client.list_invites(**params)

    async def instainstru_invites_detail(identifier: str) -> dict:
        """Get full details of an invite by ID or code."""
        return await client.get_invite_detail(identifier)

    mcp.tool()(instainstru_invites_preview)
    mcp.tool()(instainstru_invites_send)
    mcp.tool()(instainstru_invites_list)
    mcp.tool()(instainstru_invites_detail)

    return {
        "instainstru_invites_preview": instainstru_invites_preview,
        "instainstru_invites_send": instainstru_invites_send,
        "instainstru_invites_list": instainstru_invites_list,
        "instainstru_invites_detail": instainstru_invites_detail,
    }
