"""Webhook ledger tools for viewing and replaying webhooks."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_webhooks_list(
        source: str | None = None,
        status: str | None = None,
        event_type: str | None = None,
        since_hours: int = 24,
        limit: int = 50,
    ) -> dict:
        """List webhook events from the ledger."""
        return await client.get_webhooks(
            source=source,
            status=status,
            event_type=event_type,
            since_hours=since_hours,
            limit=limit,
        )

    async def instainstru_webhooks_failed(
        source: str | None = None,
        since_hours: int = 24,
        limit: int = 50,
    ) -> dict:
        """List failed webhooks for review/replay."""
        return await client.get_failed_webhooks(
            source=source,
            since_hours=since_hours,
            limit=limit,
        )

    async def instainstru_webhook_detail(event_id: str) -> dict:
        """Get full details of a webhook event."""
        return await client.get_webhook_detail(event_id)

    async def instainstru_webhook_replay(event_id: str, dry_run: bool = True) -> dict:
        """Replay a webhook event (dry-run by default)."""
        return await client.replay_webhook(event_id, dry_run=dry_run)

    mcp.tool()(instainstru_webhooks_list)
    mcp.tool()(instainstru_webhooks_failed)
    mcp.tool()(instainstru_webhook_detail)
    mcp.tool()(instainstru_webhook_replay)

    return {
        "instainstru_webhooks_list": instainstru_webhooks_list,
        "instainstru_webhooks_failed": instainstru_webhooks_failed,
        "instainstru_webhook_detail": instainstru_webhook_detail,
        "instainstru_webhook_replay": instainstru_webhook_replay,
    }


__all__ = [
    "register_tools",
]
