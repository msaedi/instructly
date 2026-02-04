"""Admin communication tools for MCP workflows."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import re
from string import Formatter
from typing import Any, Iterable, cast
from uuid import uuid4

from jinja2 import meta
from sqlalchemy.orm import Session

from app.core.constants import BRAND_NAME, SUPPORT_EMAIL
from app.core.exceptions import ConflictException, MCPTokenError, ValidationException
from app.repositories.communication_repository import CommunicationRepository
from app.repositories.factory import RepositoryFactory
from app.schemas.admin_communications import (
    AnnouncementAudience,
    AnnouncementExecuteResponse,
    AnnouncementPreviewResponse,
    BulkNotificationExecuteResponse,
    BulkNotificationPreviewResponse,
    BulkTarget,
    BulkUserType,
    CommunicationChannel,
    CommunicationStatus,
    EmailPreviewResponse,
    NotificationHistoryEntry,
    NotificationHistoryResponse,
    NotificationHistorySummary,
    NotificationTemplatesResponse,
    RenderedContent,
    TemplateInfo,
)
from app.services.audit_service import AuditService
from app.services.base import BaseService
from app.services.email import EmailService
from app.services.mcp_confirm_token_service import MCPConfirmTokenService
from app.services.mcp_idempotency_service import MCPIdempotencyService
from app.services.notification_preference_service import NotificationPreferenceService
from app.services.notification_templates import NotificationTemplate
from app.services.push_notification_service import PushNotificationService
from app.services.template_registry import TemplateRegistry
from app.services.template_service import TemplateService

logger = logging.getLogger(__name__)

STANDARD_VARIABLES = {
    "platform_name": BRAND_NAME,
    "support_email": SUPPORT_EMAIL,
}

TEST_EMAIL_LIMIT = 10
TEST_EMAIL_WINDOW = timedelta(hours=1)

_test_email_log: dict[str, list[datetime]] = {}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_schedule(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _extract_fields(template: str) -> set[str]:
    formatter = Formatter()
    fields = set()
    try:
        for _, field_name, _, _ in formatter.parse(template):
            if field_name:
                fields.add(field_name.split(".")[0])
    except ValueError:
        return set()
    return fields


def _render_template(template: str, variables: dict[str, Any]) -> tuple[str, list[str]]:
    fields = _extract_fields(template)
    missing = sorted(field for field in fields if field not in variables)
    safe_vars = defaultdict(str, variables)
    try:
        rendered = template.format_map(safe_vars)
    except Exception:
        rendered = template
    return rendered, missing


def _strip_html(html: str) -> str:
    text = re.sub(r"<[^>]+>", "", html)
    return re.sub(r"\s+", " ", text).strip()


class CommunicationAdminService(BaseService):
    """Admin communications with preview/execute guardrails."""

    CONFIRM_TOKEN_TTL = timedelta(minutes=10)

    def __init__(
        self,
        db: Session,
        *,
        communication_repo: CommunicationRepository | None = None,
        notification_preferences: NotificationPreferenceService | None = None,
        email_service: EmailService | None = None,
        template_service: TemplateService | None = None,
        push_service: PushNotificationService | None = None,
        confirm_service: MCPConfirmTokenService | None = None,
        idempotency_service: MCPIdempotencyService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        super().__init__(db)
        self.communication_repo = communication_repo or CommunicationRepository(db)
        self.notification_repo = RepositoryFactory.create_notification_repository(db)
        self.delivery_repo = RepositoryFactory.create_notification_delivery_repository(db)
        self.preference_service = notification_preferences or NotificationPreferenceService(
            db, self.notification_repo
        )
        self.email_service = email_service or EmailService(db)
        self.template_service = template_service or TemplateService(db)
        self.push_service = push_service or PushNotificationService(db, self.notification_repo)
        self.confirm_service = confirm_service or MCPConfirmTokenService(db)
        self.idempotency_service = idempotency_service or MCPIdempotencyService(db)
        self.audit_service = audit_service or AuditService(db)

    @BaseService.measure_operation("mcp_communications.preview_announcement")
    def preview_announcement(
        self,
        *,
        audience: AnnouncementAudience,
        channels: list[CommunicationChannel],
        title: str,
        body: str,
        subject: str | None,
        schedule_at: datetime | None,
        high_priority: bool,
        actor_id: str,
    ) -> AnnouncementPreviewResponse:
        schedule_at = _normalize_schedule(schedule_at)
        user_ids = self._audience_user_ids(audience)
        samples = self.communication_repo.list_users_by_ids(user_ids[:3])
        sample_user = samples[0] if samples else None
        channel_breakdown = self._channel_breakdown(user_ids, channels)
        rendered = self._render_content(title, body, subject, sample_user)
        warnings = self._audience_warnings(len(user_ids), schedule_at)

        idempotency_key = f"comm_{uuid4().hex}"
        payload = {
            "audience": audience.value,
            "channels": [channel.value for channel in channels],
            "title": title,
            "body": body,
            "subject": subject,
            "schedule_at": schedule_at.isoformat() if schedule_at else None,
            "high_priority": high_priority,
            "idempotency_key": idempotency_key,
        }
        confirm_token, _ = self.confirm_service.generate_token(
            payload,
            actor_id=actor_id,
            ttl_minutes=int(self.CONFIRM_TOKEN_TTL.total_seconds() // 60),
        )

        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="COMMUNICATION_ANNOUNCEMENT_PREVIEW",
            resource_type="communication",
            resource_id=idempotency_key,
            metadata={"audience": audience.value, "channels": payload["channels"]},
        )

        return AnnouncementPreviewResponse(
            audience_size=len(user_ids),
            channel_breakdown=channel_breakdown,
            rendered_content=rendered,
            warnings=warnings,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    @BaseService.measure_operation("mcp_communications.execute_announcement")
    def execute_announcement(
        self,
        *,
        confirm_token: str,
        idempotency_key: str,
        actor_id: str,
    ) -> AnnouncementExecuteResponse:
        payload = self._decode_confirm_payload(confirm_token, actor_id)
        if payload.get("idempotency_key") != idempotency_key:
            raise ValidationException("Idempotency key mismatch", code="IDEMPOTENCY_MISMATCH")

        already_done, cached = self._check_idempotency(
            idempotency_key,
            operation="mcp_communications.announcement",
        )
        if already_done:
            if cached is None:
                raise ConflictException("idempotency_in_progress")
            return AnnouncementExecuteResponse.model_validate(cached)

        schedule_at = _normalize_schedule(self._parse_datetime(payload.get("schedule_at")))
        audience = AnnouncementAudience(payload.get("audience"))
        channels = [CommunicationChannel(value) for value in payload.get("channels", [])]
        title = str(payload.get("title") or "")
        body = str(payload.get("body") or "")
        subject = payload.get("subject")
        high_priority = bool(payload.get("high_priority"))

        user_ids = self._audience_user_ids(audience)
        status, channel_results = self._execute_send(
            user_ids=user_ids,
            channels=channels,
            title=title,
            body=body,
            subject=subject,
            schedule_at=schedule_at,
            high_priority=high_priority,
            kind="announcement",
            actor_id=actor_id,
            batch_id=idempotency_key,
        )

        response = AnnouncementExecuteResponse(
            success=True,
            status=status,
            batch_id=idempotency_key,
            audience_size=len(user_ids),
            scheduled_for=schedule_at if status == CommunicationStatus.SCHEDULED.value else None,
            channel_results=channel_results,
        )
        self._store_idempotency(idempotency_key, response.model_dump())
        return response

    @BaseService.measure_operation("mcp_communications.preview_bulk")
    def preview_bulk_notification(
        self,
        *,
        target: BulkTarget,
        channels: list[CommunicationChannel],
        title: str,
        body: str,
        subject: str | None,
        variables: dict[str, str],
        schedule_at: datetime | None,
        actor_id: str,
    ) -> BulkNotificationPreviewResponse:
        schedule_at = _normalize_schedule(schedule_at)
        user_ids = self._bulk_user_ids(target)
        samples = self.communication_repo.list_users_by_ids(user_ids[:3])
        sample_user = samples[0] if samples else None
        channel_breakdown = self._channel_breakdown(user_ids, channels)
        rendered = self._render_content(title, body, subject, sample_user, variables)
        warnings = self._audience_warnings(len(user_ids), schedule_at)

        idempotency_key = f"comm_{uuid4().hex}"
        payload = {
            "target": target.model_dump(),
            "channels": [channel.value for channel in channels],
            "title": title,
            "body": body,
            "subject": subject,
            "variables": variables,
            "schedule_at": schedule_at.isoformat() if schedule_at else None,
            "idempotency_key": idempotency_key,
        }
        confirm_token, _ = self.confirm_service.generate_token(
            payload,
            actor_id=actor_id,
            ttl_minutes=int(self.CONFIRM_TOKEN_TTL.total_seconds() // 60),
        )

        self.audit_service.log(
            actor_id=actor_id,
            actor_type="mcp",
            action="COMMUNICATION_BULK_PREVIEW",
            resource_type="communication",
            resource_id=idempotency_key,
            metadata={"channels": payload["channels"]},
        )

        return BulkNotificationPreviewResponse(
            audience_size=len(user_ids),
            channel_breakdown=channel_breakdown,
            sample_recipients=[self._serialize_user(user) for user in samples],
            rendered_content=rendered,
            warnings=warnings,
            confirm_token=confirm_token,
            idempotency_key=idempotency_key,
        )

    @BaseService.measure_operation("mcp_communications.execute_bulk")
    def execute_bulk_notification(
        self,
        *,
        confirm_token: str,
        idempotency_key: str,
        actor_id: str,
    ) -> BulkNotificationExecuteResponse:
        payload = self._decode_confirm_payload(confirm_token, actor_id)
        if payload.get("idempotency_key") != idempotency_key:
            raise ValidationException("Idempotency key mismatch", code="IDEMPOTENCY_MISMATCH")

        already_done, cached = self._check_idempotency(
            idempotency_key,
            operation="mcp_communications.bulk",
        )
        if already_done:
            if cached is None:
                raise ConflictException("idempotency_in_progress")
            return BulkNotificationExecuteResponse.model_validate(cached)

        target_payload = payload.get("target") or {}
        target = BulkTarget.model_validate(target_payload)
        schedule_at = _normalize_schedule(self._parse_datetime(payload.get("schedule_at")))
        channels = [CommunicationChannel(value) for value in payload.get("channels", [])]
        title = str(payload.get("title") or "")
        body = str(payload.get("body") or "")
        subject = payload.get("subject")
        variables = payload.get("variables") or {}

        user_ids = self._bulk_user_ids(target)
        status, channel_results = self._execute_send(
            user_ids=user_ids,
            channels=channels,
            title=title,
            body=body,
            subject=subject,
            schedule_at=schedule_at,
            variables=variables,
            high_priority=False,
            kind="bulk",
            actor_id=actor_id,
            batch_id=idempotency_key,
        )

        response = BulkNotificationExecuteResponse(
            success=True,
            status=status,
            batch_id=idempotency_key,
            audience_size=len(user_ids),
            scheduled_for=schedule_at if status == CommunicationStatus.SCHEDULED.value else None,
            channel_results=channel_results,
        )
        self._store_idempotency(idempotency_key, response.model_dump())
        return response

    @BaseService.measure_operation("mcp_communications.history")
    def notification_history(
        self,
        *,
        kind: str | None,
        channel: str | None,
        status: str | None,
        start_date: datetime | None,
        end_date: datetime | None,
        creator_id: str | None,
        limit: int = 100,
    ) -> NotificationHistoryResponse:
        event_types = None
        if kind == "announcement":
            event_types = ["admin.communication.announcement"]
        elif kind == "bulk":
            event_types = ["admin.communication.bulk"]

        records = self.communication_repo.list_notification_deliveries(
            event_types=event_types,
            start=start_date,
            end=end_date,
            limit=limit,
        )

        entries: list[NotificationHistoryEntry] = []
        for record in records:
            payload = record.payload or {}
            entry = self._history_entry_from_payload(record.delivered_at, payload)
            if channel and channel not in entry.channels:
                continue
            if status and entry.status != status:
                continue
            if creator_id and entry.created_by != creator_id:
                continue
            entries.append(entry)

        summary = self._history_summary(entries)
        return NotificationHistoryResponse(items=entries, summary=summary)

    @BaseService.measure_operation("mcp_communications.templates")
    def notification_templates(self) -> NotificationTemplatesResponse:
        templates = self._collect_notification_templates()
        result: list[TemplateInfo] = []
        for template in templates:
            required = self._template_required_variables(template)
            optional = sorted(set(STANDARD_VARIABLES.keys()) - set(required))
            channels = ["in_app", "push"]
            if template.email_template is not None:
                channels.append("email")
            usage = self.communication_repo.count_notification_deliveries(
                f"admin.template.{template.type}"
            )
            result.append(
                TemplateInfo(
                    template_id=template.type,
                    category=template.category,
                    channels=channels,
                    required_variables=sorted(required),
                    optional_variables=optional,
                    usage_count=usage,
                )
            )
        return NotificationTemplatesResponse(templates=result)

    @BaseService.measure_operation("mcp_communications.email_preview")
    def email_preview(
        self,
        *,
        template: str,
        variables: dict[str, str],
        subject: str | None,
        test_send_to: str | None,
        actor_id: str,
    ) -> EmailPreviewResponse:
        try:
            template_enum = TemplateRegistry(template)
        except ValueError as exc:
            raise ValidationException("Unknown template", code="TEMPLATE_NOT_FOUND") from exc

        context = self._template_context(None, variables)
        if subject:
            context["subject"] = subject

        source = self.template_service.env.loader.get_source(
            self.template_service.env, template_enum.value
        )[0]
        parsed = self.template_service.env.parse(source)
        required = meta.find_undeclared_variables(parsed)
        missing = sorted(var for var in required if var not in context)

        html_content = self.template_service.render_template(template_enum, context)
        text_content = _strip_html(html_content)
        valid = not missing

        test_success: bool | None = None
        if test_send_to:
            self._check_test_email_limit(actor_id)
            if valid:
                try:
                    self.email_service.send_email(
                        to_email=test_send_to,
                        subject=subject or "Preview",
                        html_content=html_content,
                        text_content=text_content,
                        template=template_enum,
                    )
                    test_success = True
                except Exception:
                    test_success = False
            else:
                test_success = False

        return EmailPreviewResponse(
            template=template_enum.value,
            subject=subject or "Preview",
            html_content=html_content,
            text_content=text_content,
            missing_variables=missing,
            valid=valid,
            test_send_success=test_success,
        )

    def _audience_user_ids(self, audience: AnnouncementAudience) -> list[str]:
        if audience == AnnouncementAudience.ALL_USERS:
            return list(
                set(self.communication_repo.list_user_ids_by_role("student"))
                | set(self.communication_repo.list_user_ids_by_role("instructor"))
            )
        if audience == AnnouncementAudience.ALL_STUDENTS:
            return self.communication_repo.list_user_ids_by_role("student")
        if audience == AnnouncementAudience.ALL_INSTRUCTORS:
            return self.communication_repo.list_user_ids_by_role("instructor")
        if audience == AnnouncementAudience.ACTIVE_STUDENTS:
            since = _now_utc() - timedelta(days=30)
            return self.communication_repo.list_active_user_ids(since, "student")
        if audience == AnnouncementAudience.ACTIVE_INSTRUCTORS:
            since = _now_utc() - timedelta(days=30)
            return self.communication_repo.list_active_user_ids(since, "instructor")
        if audience == AnnouncementAudience.FOUNDING_INSTRUCTORS:
            return self.communication_repo.list_founding_instructor_ids()
        return []

    def _bulk_user_ids(self, target: BulkTarget) -> list[str]:
        base_ids: set[str]
        if target.user_type == BulkUserType.STUDENT:
            base_ids = set(self.communication_repo.list_user_ids_by_role("student"))
        elif target.user_type == BulkUserType.INSTRUCTOR:
            base_ids = set(self.communication_repo.list_user_ids_by_role("instructor"))
        else:
            base_ids = set(self.communication_repo.list_user_ids_by_role("student")) | set(
                self.communication_repo.list_user_ids_by_role("instructor")
            )

        if target.user_ids:
            base_ids &= set(target.user_ids)

        if target.active_within_days:
            since = _now_utc() - timedelta(days=target.active_within_days)
            active_ids = set()
            active_ids |= set(self.communication_repo.list_active_user_ids(since, "student"))
            active_ids |= set(self.communication_repo.list_active_user_ids(since, "instructor"))
            base_ids &= active_ids

        if target.categories:
            category_ids = self.communication_repo.resolve_category_ids(target.categories)
            ids = set(self.communication_repo.list_student_ids_by_categories(category_ids)) | set(
                self.communication_repo.list_instructor_ids_by_categories(category_ids)
            )
            base_ids &= ids

        if target.locations:
            region_ids = self.communication_repo.resolve_region_ids(target.locations)
            instructor_ids = set(self.communication_repo.list_instructor_ids_by_regions(region_ids))
            student_ids = set(self.communication_repo.list_student_ids_by_zip(target.locations))
            base_ids &= instructor_ids | student_ids

        return list(base_ids)

    def _channel_breakdown(
        self, user_ids: list[str], channels: Iterable[CommunicationChannel]
    ) -> dict[str, int]:
        breakdown: dict[str, int] = {channel.value: 0 for channel in channels}
        push_users = self.communication_repo.list_push_subscription_user_ids(user_ids)
        users = self.communication_repo.list_users_by_ids(user_ids)
        user_lookup = {user.id: user for user in users}

        for user_id in user_ids:
            user = user_lookup.get(user_id)
            for channel in channels:
                if self._is_channel_eligible(user, user_id, channel, push_users):
                    breakdown[channel.value] += 1
        return breakdown

    def _is_channel_eligible(
        self,
        user: Any,
        user_id: str,
        channel: CommunicationChannel,
        push_users: set[str],
    ) -> bool:
        category = "system_updates"
        if channel == CommunicationChannel.EMAIL:
            if not user or not getattr(user, "email", None):
                return False
            return self.preference_service.is_enabled(user_id, category, "email")
        if channel == CommunicationChannel.PUSH:
            if user_id not in push_users:
                return False
            return self.preference_service.is_enabled(user_id, category, "push")
        return True

    def _render_content(
        self,
        title: str,
        body: str,
        subject: str | None,
        user: Any,
        variables: dict[str, str] | None = None,
    ) -> RenderedContent:
        context = self._template_context(user, variables or {})
        rendered_title, _ = _render_template(title, context)
        rendered_body, _ = _render_template(body, context)
        rendered_subject = None
        if subject:
            rendered_subject, _ = _render_template(subject, context)
        html_body = f"<p>{rendered_body}</p>" if rendered_body else None
        text_body = rendered_body
        return RenderedContent(
            subject=rendered_subject,
            title=rendered_title,
            body=rendered_body,
            html_body=html_body,
            text_body=text_body,
        )

    def _audience_warnings(self, audience_size: int, schedule_at: datetime | None) -> list[str]:
        warnings = []
        if audience_size > 1000 and schedule_at is None:
            warnings.append("Large audience - consider scheduling to avoid rate limits")
        if audience_size > 5000:
            warnings.append("Very large audience - will be sent in batches over time")
        return warnings

    def _serialize_user(self, user: Any) -> dict[str, Any]:
        return {
            "user_id": getattr(user, "id", ""),
            "email": getattr(user, "email", None),
            "first_name": getattr(user, "first_name", None),
            "last_name": getattr(user, "last_name", None),
        }

    def _template_context(self, user: Any, variables: dict[str, Any]) -> dict[str, Any]:
        context: dict[str, Any] = {
            **STANDARD_VARIABLES,
            "current_year": _now_utc().year,
            "platform_name": BRAND_NAME,
        }
        if user is not None:
            context.update(
                {
                    "user_first_name": getattr(user, "first_name", ""),
                    "user_email": getattr(user, "email", ""),
                }
            )
        context.update(variables)
        return context

    def _execute_send(
        self,
        *,
        user_ids: list[str],
        channels: list[CommunicationChannel],
        title: str,
        body: str,
        subject: str | None,
        schedule_at: datetime | None,
        variables: dict[str, str] | None = None,
        high_priority: bool,
        kind: str,
        actor_id: str,
        batch_id: str,
    ) -> tuple[str, dict[str, dict[str, int]]]:
        if schedule_at and schedule_at > _now_utc():
            status = CommunicationStatus.SCHEDULED.value
            channel_results = {
                channel.value: {"sent": 0, "delivered": 0, "failed": 0} for channel in channels
            }
            self._record_history(
                batch_id=batch_id,
                kind=kind,
                status=status,
                channels=channels,
                audience_size=len(user_ids),
                subject=subject,
                title=title,
                results=channel_results,
                created_by=actor_id,
                scheduled_for=schedule_at,
            )
            return status, channel_results

        channel_results = {
            channel.value: {"sent": 0, "delivered": 0, "failed": 0} for channel in channels
        }
        push_users = self.communication_repo.list_push_subscription_user_ids(user_ids)
        users = self.communication_repo.list_users_by_ids(user_ids)
        user_lookup = {user.id: user for user in users}

        for user_id in user_ids:
            user = user_lookup.get(user_id)
            context = self._template_context(user, variables or {})
            rendered_title, _ = _render_template(title, context)
            rendered_body, _ = _render_template(body, context)
            rendered_subject = None
            if subject:
                rendered_subject, _ = _render_template(subject, context)

            if CommunicationChannel.IN_APP in channels:
                self.notification_repo.create_notification(
                    user_id=user_id,
                    category="system_updates",
                    type=f"admin_{kind}",
                    title=rendered_title,
                    body=rendered_body,
                    data={"batch_id": batch_id},
                )
                channel_results[CommunicationChannel.IN_APP.value]["sent"] += 1
                channel_results[CommunicationChannel.IN_APP.value]["delivered"] += 1

            if CommunicationChannel.PUSH in channels and self._is_channel_eligible(
                user, user_id, CommunicationChannel.PUSH, push_users
            ):
                try:
                    result = self.push_service.send_push_notification(
                        user_id=user_id,
                        title=rendered_title,
                        body=rendered_body,
                        url=None,
                        data={
                            "batch_id": batch_id,
                            "priority": "high" if high_priority else "normal",
                        },
                    )
                    channel_results[CommunicationChannel.PUSH.value]["sent"] += result.get(
                        "sent", 0
                    )
                    channel_results[CommunicationChannel.PUSH.value]["delivered"] += result.get(
                        "sent", 0
                    )
                    channel_results[CommunicationChannel.PUSH.value]["failed"] += result.get(
                        "failed", 0
                    ) + result.get("expired", 0)
                except Exception:
                    channel_results[CommunicationChannel.PUSH.value]["failed"] += 1

            if CommunicationChannel.EMAIL in channels and self._is_channel_eligible(
                user, user_id, CommunicationChannel.EMAIL, push_users
            ):
                if user is None or not getattr(user, "email", None):
                    channel_results[CommunicationChannel.EMAIL.value]["failed"] += 1
                else:
                    html_body = f"<p>{rendered_body}</p>"
                    try:
                        self.email_service.send_email(
                            to_email=user.email,
                            subject=rendered_subject or rendered_title,
                            html_content=html_body,
                            text_content=rendered_body,
                        )
                        channel_results[CommunicationChannel.EMAIL.value]["sent"] += 1
                        channel_results[CommunicationChannel.EMAIL.value]["delivered"] += 1
                    except Exception:
                        channel_results[CommunicationChannel.EMAIL.value]["failed"] += 1

        status = CommunicationStatus.SENT.value
        self._record_history(
            batch_id=batch_id,
            kind=kind,
            status=status,
            channels=channels,
            audience_size=len(user_ids),
            subject=subject,
            title=title,
            results=channel_results,
            created_by=actor_id,
            scheduled_for=None,
        )
        return status, channel_results

    def _record_history(
        self,
        *,
        batch_id: str,
        kind: str,
        status: str,
        channels: list[CommunicationChannel],
        audience_size: int,
        subject: str | None,
        title: str,
        results: dict[str, dict[str, int]],
        created_by: str,
        scheduled_for: datetime | None,
    ) -> None:
        payload = {
            "batch_id": batch_id,
            "kind": kind,
            "status": status,
            "channels": [channel.value for channel in channels],
            "audience_size": audience_size,
            "subject": subject,
            "title": title,
            "sent": {channel: values.get("sent", 0) for channel, values in results.items()},
            "delivered": {
                channel: values.get("delivered", 0) for channel, values in results.items()
            },
            "failed": {channel: values.get("failed", 0) for channel, values in results.items()},
            "created_by": created_by,
            "scheduled_for": scheduled_for.isoformat() if scheduled_for else None,
            "open_rate": "0",
            "click_rate": "0",
        }
        self.delivery_repo.record_delivery(
            event_type=f"admin.communication.{kind}",
            idempotency_key=batch_id,
            payload=payload,
        )

    def _history_entry_from_payload(
        self, delivered_at: datetime, payload: dict[str, Any]
    ) -> NotificationHistoryEntry:
        channels = payload.get("channels") or []
        return NotificationHistoryEntry(
            batch_id=str(payload.get("batch_id")),
            kind=str(payload.get("kind")),
            status=str(payload.get("status")),
            channels=[str(channel) for channel in channels],
            created_at=delivered_at,
            scheduled_for=self._parse_datetime(payload.get("scheduled_for")),
            created_by=payload.get("created_by"),
            audience_size=int(payload.get("audience_size") or 0),
            subject=payload.get("subject"),
            title=payload.get("title"),
            sent={str(k): int(v) for k, v in (payload.get("sent") or {}).items()},
            delivered={str(k): int(v) for k, v in (payload.get("delivered") or {}).items()},
            failed={str(k): int(v) for k, v in (payload.get("failed") or {}).items()},
            open_rate=Decimal(str(payload.get("open_rate") or "0")),
            click_rate=Decimal(str(payload.get("click_rate") or "0")),
        )

    def _history_summary(
        self, entries: list[NotificationHistoryEntry]
    ) -> NotificationHistorySummary:
        sent = sum(sum(entry.sent.values()) for entry in entries)
        delivered = sum(sum(entry.delivered.values()) for entry in entries)
        failed = sum(sum(entry.failed.values()) for entry in entries)
        open_rate = (
            sum(entry.open_rate for entry in entries) / Decimal(len(entries))
            if entries
            else Decimal("0")
        )
        click_rate = (
            sum(entry.click_rate for entry in entries) / Decimal(len(entries))
            if entries
            else Decimal("0")
        )
        return NotificationHistorySummary(
            total=len(entries),
            sent=sent,
            delivered=delivered,
            failed=failed,
            open_rate=open_rate,
            click_rate=click_rate,
        )

    def _collect_notification_templates(self) -> list[NotificationTemplate]:
        import app.services.notification_templates as templates

        result: list[NotificationTemplate] = []
        for value in templates.__dict__.values():
            if isinstance(value, NotificationTemplate):
                result.append(value)
        return result

    def _template_required_variables(self, template: NotificationTemplate) -> list[str]:
        fields = set()
        fields |= _extract_fields(template.body_template)
        if template.url_template:
            fields |= _extract_fields(template.url_template)
        if template.email_subject_template:
            fields |= _extract_fields(template.email_subject_template)
        return sorted(field for field in fields if field not in STANDARD_VARIABLES)

    def _decode_confirm_payload(self, confirm_token: str, actor_id: str) -> dict[str, Any]:
        try:
            token_data = self.confirm_service.decode_token(confirm_token)
        except MCPTokenError as exc:
            raise exc
        payload = token_data.get("payload")
        if not isinstance(payload, dict):
            raise ValidationException("Invalid confirm token payload")
        self.confirm_service.validate_token(confirm_token, payload, actor_id=actor_id)
        return payload

    def _parse_datetime(self, value: Any) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _check_idempotency(
        self, idempotency_key: str, operation: str
    ) -> tuple[bool, dict[str, Any] | None]:
        return cast(
            tuple[bool, dict[str, Any] | None],
            self._run_async(self.idempotency_service.check_and_store(idempotency_key, operation)),
        )

    def _store_idempotency(self, idempotency_key: str, payload: dict[str, Any]) -> None:
        self._run_async(self.idempotency_service.store_result(idempotency_key, payload))

    def _run_async(self, coro: Any) -> Any:
        try:
            return asyncio.run(coro)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    def _check_test_email_limit(self, actor_id: str) -> None:
        now = _now_utc()
        window_start = now - TEST_EMAIL_WINDOW
        entries = [stamp for stamp in _test_email_log.get(actor_id, []) if stamp >= window_start]
        if len(entries) >= TEST_EMAIL_LIMIT:
            raise ValidationException(
                "Test email rate limit exceeded", code="TEST_EMAIL_RATE_LIMIT"
            )
        entries.append(now)
        _test_email_log[actor_id] = entries
