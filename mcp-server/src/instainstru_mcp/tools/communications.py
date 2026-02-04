"""MCP tools for admin communications."""

from __future__ import annotations

from fastmcp import FastMCP

from ..client import InstaInstruClient


def register_tools(mcp: FastMCP, client: InstaInstruClient) -> dict[str, object]:
    async def instainstru_announcement_preview(
        audience: str,
        channels: list[str],
        title: str,
        body: str,
        subject: str | None = None,
        schedule_at: str | None = None,
        high_priority: bool = False,
    ) -> dict:
        """
        Preview a platform-wide announcement.

        Args:
            audience: all_users, all_students, all_instructors, active_students,
                active_instructors, founding_instructors
            channels: email, push, in_app
            title: Announcement title
            body: Announcement body
            subject: Optional email subject
            schedule_at: Optional ISO timestamp to schedule delivery
            high_priority: Flag urgent announcements
        """
        return await client.announcement_preview(
            audience=audience,
            channels=channels,
            title=title,
            body=body,
            subject=subject,
            schedule_at=schedule_at,
            high_priority=high_priority,
        )

    async def instainstru_announcement_execute(
        confirm_token: str,
        idempotency_key: str,
    ) -> dict:
        """
        Execute a previewed announcement send.

        Args:
            confirm_token: Token from preview
            idempotency_key: Key from preview
        """
        return await client.announcement_execute(
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    async def instainstru_bulk_notification_preview(
        target: dict,
        channels: list[str],
        title: str,
        body: str,
        subject: str | None = None,
        variables: dict[str, str] | None = None,
        schedule_at: str | None = None,
    ) -> dict:
        """
        Preview a bulk notification send.

        Args:
            target: Targeting payload (user_type, user_ids, categories, locations, active_within_days)
            channels: email, push, in_app
            title: Notification title
            body: Notification body
            subject: Optional email subject
            variables: Optional template variables
            schedule_at: Optional ISO timestamp to schedule delivery
        """
        return await client.bulk_notification_preview(
            target=target,
            channels=channels,
            title=title,
            body=body,
            subject=subject,
            variables=variables,
            schedule_at=schedule_at,
        )

    async def instainstru_bulk_notification_execute(
        confirm_token: str,
        idempotency_key: str,
    ) -> dict:
        """
        Execute a previewed bulk notification.

        Args:
            confirm_token: Token from preview
            idempotency_key: Key from preview
        """
        return await client.bulk_notification_execute(
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    async def instainstru_notification_history(
        kind: str | None = None,
        channel: str | None = None,
        status: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        creator_id: str | None = None,
        limit: int = 100,
    ) -> dict:
        """
        Retrieve notification history with filters.

        Args:
            kind: announcement or bulk
            channel: email, push, in_app
            status: sent, scheduled, failed
            start_date: ISO timestamp filter
            end_date: ISO timestamp filter
            creator_id: Admin identifier
            limit: Max results
        """
        return await client.notification_history(
            kind=kind,
            channel=channel,
            status=status,
            start_date=start_date,
            end_date=end_date,
            creator_id=creator_id,
            limit=limit,
        )

    async def instainstru_notification_templates() -> dict:
        """
        List available notification templates.
        """
        return await client.notification_templates()

    async def instainstru_email_preview(
        template: str,
        variables: dict[str, str] | None = None,
        subject: str | None = None,
        test_send_to: str | None = None,
    ) -> dict:
        """
        Render an email template preview.

        Args:
            template: Template registry key
            variables: Variables for rendering
            subject: Optional override subject
            test_send_to: Optional email address to send a test
        """
        return await client.email_preview(
            template=template,
            variables=variables,
            subject=subject,
            test_send_to=test_send_to,
        )

    mcp.tool()(instainstru_announcement_preview)
    mcp.tool()(instainstru_announcement_execute)
    mcp.tool()(instainstru_bulk_notification_preview)
    mcp.tool()(instainstru_bulk_notification_execute)
    mcp.tool()(instainstru_notification_history)
    mcp.tool()(instainstru_notification_templates)
    mcp.tool()(instainstru_email_preview)

    return {
        "instainstru_announcement_preview": instainstru_announcement_preview,
        "instainstru_announcement_execute": instainstru_announcement_execute,
        "instainstru_bulk_notification_preview": instainstru_bulk_notification_preview,
        "instainstru_bulk_notification_execute": instainstru_bulk_notification_execute,
        "instainstru_notification_history": instainstru_notification_history,
        "instainstru_notification_templates": instainstru_notification_templates,
        "instainstru_email_preview": instainstru_email_preview,
    }
