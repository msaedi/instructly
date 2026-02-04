from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.core.exceptions import ConflictException, MCPTokenError, ValidationException
from app.schemas.admin_communications import (
    AnnouncementAudience,
    BulkTarget,
    BulkUserType,
    CommunicationChannel,
)
from app.services.communication_admin_service import (
    CommunicationAdminService,
    _render_template,
    _strip_html,
    _test_email_log,
)
from app.services.notification_templates import NotificationTemplate
from app.services.template_registry import TemplateRegistry
from app.services.template_service import TemplateService


class StubConfirmService:
    def __init__(self, payload: dict | None = None, raise_decode: bool = False) -> None:
        self.payload = payload or {}
        self.raise_decode = raise_decode
        self.generated: list[dict] = []

    def generate_token(self, payload, actor_id: str, ttl_minutes: int):
        self.payload = payload
        self.generated.append(payload)
        return "confirm_token", {}

    def decode_token(self, token: str):
        if self.raise_decode:
            raise MCPTokenError("bad_token")
        return {"payload": self.payload}

    def validate_token(self, token: str, payload: dict, actor_id: str) -> None:
        return None


class StubIdempotency:
    def __init__(self, already_done: bool = False, cached: dict | None = None) -> None:
        self.already_done = already_done
        self.cached = cached
        self.stored: list[tuple[str, dict]] = []

    async def check_and_store(self, key: str, operation: str):
        return self.already_done, self.cached

    async def store_result(self, key: str, payload: dict):
        self.stored.append((key, payload))


class StubNotificationRepo:
    def __init__(self) -> None:
        self.created: list[dict] = []

    def create_notification(self, **payload):
        self.created.append(payload)
        return payload


class StubDeliveryRepo:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record_delivery(self, **payload):
        self.records.append(payload)
        return payload


class StubPreferenceService:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.calls: list[tuple[str, str]] = []

    def is_enabled(self, user_id: str, category: str, channel: str) -> bool:
        self.calls.append((user_id, channel))
        return self.enabled


class StubEmailService:
    def __init__(self, raise_for: set[str] | None = None) -> None:
        self.raise_for = raise_for or set()
        self.sent: list[dict] = []

    def send_email(self, to_email: str, subject: str, html_content: str, text_content: str, **_kwargs):
        if to_email in self.raise_for:
            raise RuntimeError("send failed")
        self.sent.append(
            {
                "to_email": to_email,
                "subject": subject,
                "html_content": html_content,
                "text_content": text_content,
            }
        )
        return {"id": "email"}


class StubPushService:
    def __init__(self, raise_for: set[str] | None = None) -> None:
        self.raise_for = raise_for or set()
        self.calls: list[str] = []

    def send_push_notification(self, user_id: str, **_kwargs):
        self.calls.append(user_id)
        if user_id in self.raise_for:
            raise RuntimeError("push failed")
        return {"sent": 1, "failed": 0, "expired": 0}


class StubAuditService:
    def __init__(self) -> None:
        self.logs: list[dict] = []

    def log(self, **payload):
        self.logs.append(payload)


class StubCommunicationRepo:
    def __init__(self) -> None:
        self.student_ids: list[str] = ["u1", "u2"]
        self.instructor_ids: list[str] = ["u3"]
        self.active_student_ids: list[str] = ["u1"]
        self.active_instructor_ids: list[str] = ["u3"]
        self.founding_ids: list[str] = ["u3"]
        self.push_ids: set[str] = {"u1"}
        self.users = {
            "u1": SimpleNamespace(id="u1", email="u1@example.com", first_name="Ada", last_name="L"),
            "u2": SimpleNamespace(id="u2", email=None, first_name="Bob", last_name="S"),
            "u3": SimpleNamespace(id="u3", email="u3@example.com", first_name="Cec", last_name="T"),
        }
        self.category_ids: list[str] = ["cat1"]
        self.region_ids: list[str] = ["reg1"]
        self.student_category_ids: list[str] = ["u1"]
        self.instructor_category_ids: list[str] = ["u3"]
        self.student_region_ids: list[str] = ["u1"]
        self.instructor_region_ids: list[str] = ["u3"]
        self.notifications: list[SimpleNamespace] = []

    def list_users_by_ids(self, user_ids):
        return [self.users[user_id] for user_id in user_ids if user_id in self.users]

    def list_user_ids_by_role(self, role_name: str):
        return self.student_ids if role_name == "student" else self.instructor_ids

    def list_active_user_ids(self, _since, role_name: str):
        return self.active_student_ids if role_name == "student" else self.active_instructor_ids

    def list_founding_instructor_ids(self):
        return self.founding_ids

    def list_push_subscription_user_ids(self, user_ids):
        return set(user_ids) & self.push_ids

    def resolve_category_ids(self, _categories):
        return self.category_ids

    def resolve_region_ids(self, _locations):
        return self.region_ids

    def list_student_ids_by_categories(self, _category_ids):
        return self.student_category_ids

    def list_instructor_ids_by_categories(self, _category_ids):
        return self.instructor_category_ids

    def list_instructor_ids_by_regions(self, _region_ids):
        return self.instructor_region_ids

    def list_student_ids_by_zip(self, _zip_codes):
        return self.student_region_ids

    def list_notification_deliveries(self, **_kwargs):
        return self.notifications

    def count_notification_deliveries(self, _event_type: str) -> int:
        return 2


def _service(db, *, communication_repo=None, idempotency=None, confirm_service=None, email_service=None):
    service = CommunicationAdminService(
        db,
        communication_repo=communication_repo or StubCommunicationRepo(),
        notification_preferences=StubPreferenceService(),
        email_service=email_service or StubEmailService(),
        template_service=TemplateService(db),
        push_service=StubPushService(raise_for={"u2"}),
        confirm_service=confirm_service or StubConfirmService(),
        idempotency_service=idempotency or StubIdempotency(),
        audit_service=StubAuditService(),
    )
    service.notification_repo = StubNotificationRepo()
    service.delivery_repo = StubDeliveryRepo()
    return service


def test_render_template_and_strip_html_branches():
    rendered, missing = _render_template("Hello {name}", {"name": "Ada"})
    assert rendered == "Hello Ada"
    assert missing == []

    rendered, missing = _render_template("Hello {name}", {})
    assert "name" in missing

    rendered, missing = _render_template("Hello {", {})
    assert rendered == "Hello {"

    assert _strip_html("<p> Hello</p>") == "Hello"


def test_preview_announcement_basic(db):
    service = _service(db)
    response = service.preview_announcement(
        audience=AnnouncementAudience.ALL_USERS,
        channels=[CommunicationChannel.EMAIL, CommunicationChannel.PUSH, CommunicationChannel.IN_APP],
        title="Hi {user_first_name}",
        body="Body",
        subject="Subject",
        schedule_at=None,
        high_priority=False,
        actor_id="admin",
    )
    assert response.audience_size == 3
    assert response.channel_breakdown["in_app"] == 3
    assert response.confirm_token == "confirm_token"
    assert response.rendered_content.title.startswith("Hi")


def test_preview_announcement_large_warnings(db):
    repo = StubCommunicationRepo()
    repo.student_ids = [f"u{idx}" for idx in range(6001)]
    service = _service(db, communication_repo=repo)
    response = service.preview_announcement(
        audience=AnnouncementAudience.ALL_STUDENTS,
        channels=[CommunicationChannel.IN_APP],
        title="Hello",
        body="Body",
        subject=None,
        schedule_at=None,
        high_priority=False,
        actor_id="admin",
    )
    assert len(response.warnings) == 2


def test_preview_bulk_notification_serializes_and_normalizes(db):
    schedule_at = datetime(2026, 1, 1, 12, 0, 0)
    confirm_service = StubConfirmService()
    service = _service(db, confirm_service=confirm_service)
    response = service.preview_bulk_notification(
        target=BulkTarget(user_type=BulkUserType.ALL),
        channels=[CommunicationChannel.IN_APP],
        title="Hello",
        body="Body",
        subject=None,
        variables={},
        schedule_at=schedule_at,
        actor_id="admin",
    )
    assert response.sample_recipients
    payload = confirm_service.generated[0]
    assert payload["schedule_at"].endswith("+00:00")


def test_execute_announcement_idempotency_cached(db):
    cached = {
        "success": True,
        "status": "sent",
        "batch_id": "idem",
        "audience_size": 1,
        "scheduled_for": None,
        "channel_results": {"in_app": {"sent": 1, "delivered": 1, "failed": 0}},
    }
    service = _service(
        db,
        idempotency=StubIdempotency(already_done=True, cached=cached),
        confirm_service=StubConfirmService({"idempotency_key": "idem"}),
    )
    response = service.execute_announcement(
        confirm_token="confirm_token",
        idempotency_key="idem",
        actor_id="admin",
    )
    assert response.status == "sent"


def test_execute_announcement_idempotency_in_progress(db):
    service = _service(
        db,
        idempotency=StubIdempotency(already_done=True, cached=None),
        confirm_service=StubConfirmService({"idempotency_key": "idem"}),
    )
    with pytest.raises(ConflictException):
        service.execute_announcement(
            confirm_token="confirm_token",
            idempotency_key="idem",
            actor_id="admin",
        )


def test_execute_announcement_mismatch(db):
    service = _service(
        db,
        confirm_service=StubConfirmService({"idempotency_key": "other"}),
    )
    with pytest.raises(ValidationException):
        service.execute_announcement(
            confirm_token="confirm_token",
            idempotency_key="idem",
            actor_id="admin",
        )


def test_execute_announcement_scheduled(db):
    future = datetime.now(timezone.utc) + timedelta(days=1)
    payload = {
        "idempotency_key": "idem",
        "audience": "all_users",
        "channels": ["in_app"],
        "title": "Hello",
        "body": "Body",
        "subject": None,
        "schedule_at": future.isoformat(),
        "high_priority": False,
    }
    delivery_repo = StubDeliveryRepo()
    service = _service(db, confirm_service=StubConfirmService(payload))
    service.delivery_repo = delivery_repo
    response = service.execute_announcement(
        confirm_token="confirm_token",
        idempotency_key="idem",
        actor_id="admin",
    )
    assert response.status == "scheduled"
    assert delivery_repo.records


def test_execute_announcement_send_channels(db):
    payload = {
        "idempotency_key": "idem",
        "audience": "all_users",
        "channels": ["email", "push", "in_app"],
        "title": "Hello",
        "body": "Body",
        "subject": None,
        "schedule_at": None,
        "high_priority": True,
    }
    delivery_repo = StubDeliveryRepo()
    service = _service(db, confirm_service=StubConfirmService(payload))
    service.delivery_repo = delivery_repo
    service._is_channel_eligible = lambda *_args, **_kwargs: True
    response = service.execute_announcement(
        confirm_token="confirm_token",
        idempotency_key="idem",
        actor_id="admin",
    )
    assert response.status == "sent"
    assert response.channel_results["in_app"]["sent"] == 3
    assert response.channel_results["email"]["failed"] >= 1
    assert response.channel_results["push"]["failed"] >= 1


def test_execute_announcement_email_exception(db):
    payload = {
        "idempotency_key": "idem",
        "audience": "all_users",
        "channels": ["email"],
        "title": "Hello",
        "body": "Body",
        "subject": None,
        "schedule_at": None,
        "high_priority": False,
    }
    email_service = StubEmailService(raise_for={"u1@example.com"})
    service = _service(
        db,
        confirm_service=StubConfirmService(payload),
        email_service=email_service,
    )
    service._is_channel_eligible = lambda *_args, **_kwargs: True
    response = service.execute_announcement(
        confirm_token="confirm_token",
        idempotency_key="idem",
        actor_id="admin",
    )
    assert response.channel_results["email"]["failed"] >= 1


def test_execute_bulk_notification_mismatch(db):
    payload = {"idempotency_key": "other"}
    service = _service(db, confirm_service=StubConfirmService(payload))
    with pytest.raises(ValidationException):
        service.execute_bulk_notification(
            confirm_token="confirm_token",
            idempotency_key="idem",
            actor_id="admin",
        )


def test_execute_bulk_notification_cached(db):
    cached = {
        "success": True,
        "status": "sent",
        "batch_id": "idem",
        "audience_size": 1,
        "scheduled_for": None,
        "channel_results": {"in_app": {"sent": 1, "delivered": 1, "failed": 0}},
    }
    payload = {"idempotency_key": "idem"}
    service = _service(
        db,
        confirm_service=StubConfirmService(payload),
        idempotency=StubIdempotency(already_done=True, cached=cached),
    )
    response = service.execute_bulk_notification(
        confirm_token="confirm_token",
        idempotency_key="idem",
        actor_id="admin",
    )
    assert response.status == "sent"


def test_execute_bulk_notification_in_progress(db):
    payload = {"idempotency_key": "idem"}
    service = _service(
        db,
        confirm_service=StubConfirmService(payload),
        idempotency=StubIdempotency(already_done=True, cached=None),
    )
    with pytest.raises(ConflictException):
        service.execute_bulk_notification(
            confirm_token="confirm_token",
            idempotency_key="idem",
            actor_id="admin",
        )


def test_execute_bulk_notification_success(db):
    payload = {
        "idempotency_key": "idem",
        "target": {"user_type": "all"},
        "channels": ["in_app"],
        "title": "Hello",
        "body": "Body",
        "subject": "Subject",
        "variables": {},
        "schedule_at": None,
    }
    service = _service(db, confirm_service=StubConfirmService(payload))
    response = service.execute_bulk_notification(
        confirm_token="confirm_token",
        idempotency_key="idem",
        actor_id="admin",
    )
    assert response.status == "sent"


def test_bulk_user_ids_filters(db):
    repo = StubCommunicationRepo()
    service = _service(db, communication_repo=repo)
    target = BulkTarget(
        user_type=BulkUserType.STUDENT,
        user_ids=["u1", "u2"],
        categories=["cat"],
        locations=["loc"],
        active_within_days=30,
    )
    result = service._bulk_user_ids(target)
    assert result == ["u1"]

    target_all = BulkTarget(user_type=BulkUserType.ALL)
    result_all = service._bulk_user_ids(target_all)
    assert set(result_all) == {"u1", "u2", "u3"}

    target_instructor = BulkTarget(user_type=BulkUserType.INSTRUCTOR)
    result_instructor = service._bulk_user_ids(target_instructor)
    assert result_instructor == ["u3"]


def test_audience_user_ids_branches(db):
    service = _service(db)
    assert service._audience_user_ids(AnnouncementAudience.ALL_USERS)
    assert service._audience_user_ids(AnnouncementAudience.ALL_STUDENTS)
    assert service._audience_user_ids(AnnouncementAudience.ALL_INSTRUCTORS)
    assert service._audience_user_ids(AnnouncementAudience.ACTIVE_STUDENTS)
    assert service._audience_user_ids(AnnouncementAudience.ACTIVE_INSTRUCTORS)
    assert service._audience_user_ids(AnnouncementAudience.FOUNDING_INSTRUCTORS)
    assert service._audience_user_ids("unknown") == []
    context = service._template_context(None, {})
    assert "platform_name" in context


def test_notification_history_filters_and_summary(db):
    repo = StubCommunicationRepo()
    repo.notifications = [
        SimpleNamespace(
            delivered_at=datetime.now(timezone.utc),
            payload={
                "batch_id": "b1",
                "kind": "announcement",
                "status": "sent",
                "channels": ["email"],
                "audience_size": 2,
                "subject": "Hi",
                "title": "Hello",
                "sent": {"email": 2},
                "delivered": {"email": 2},
                "failed": {"email": 0},
                "open_rate": "0.5",
                "click_rate": "0.25",
                "created_by": "admin",
            },
        )
    ]
    service = _service(db, communication_repo=repo)
    response = service.notification_history(
        kind="announcement",
        channel="email",
        status="sent",
        start_date=None,
        end_date=None,
        creator_id="admin",
        limit=10,
    )
    assert response.summary.total == 1
    assert response.summary.open_rate == Decimal("0.5")


def test_notification_history_filter_continue_paths(db):
    repo = StubCommunicationRepo()
    repo.notifications = [
        SimpleNamespace(
            delivered_at=datetime.now(timezone.utc),
            payload={
                "batch_id": "b1",
                "kind": "bulk",
                "status": "sent",
                "channels": ["push"],
                "audience_size": 2,
                "sent": {"push": 2},
                "delivered": {"push": 2},
                "failed": {"push": 0},
            },
        ),
        SimpleNamespace(
            delivered_at=datetime.now(timezone.utc),
            payload={
                "batch_id": "b2",
                "kind": "bulk",
                "status": "failed",
                "channels": ["email"],
                "audience_size": 2,
                "sent": {"email": 2},
                "delivered": {"email": 1},
                "failed": {"email": 1},
                "created_by": "admin",
            },
        ),
        SimpleNamespace(
            delivered_at=datetime.now(timezone.utc),
            payload={
                "batch_id": "b3",
                "kind": "bulk",
                "status": "sent",
                "channels": ["email"],
                "audience_size": 2,
                "sent": {"email": 2},
                "delivered": {"email": 2},
                "failed": {"email": 0},
                "created_by": "other",
            },
        ),
        SimpleNamespace(
            delivered_at=datetime.now(timezone.utc),
            payload={
                "batch_id": "b4",
                "kind": "bulk",
                "status": "sent",
                "channels": ["email"],
                "audience_size": 2,
                "sent": {"email": 2},
                "delivered": {"email": 2},
                "failed": {"email": 0},
                "created_by": "admin",
            },
        ),
    ]
    service = _service(db, communication_repo=repo)
    response = service.notification_history(
        kind="bulk",
        channel="email",
        status="sent",
        start_date=None,
        end_date=None,
        creator_id="admin",
        limit=10,
    )
    assert response.summary.total == 1


def test_notification_history_unknown_kind(db):
    repo = StubCommunicationRepo()
    repo.notifications = []
    service = _service(db, communication_repo=repo)
    response = service.notification_history(
        kind="other",
        channel=None,
        status=None,
        start_date=None,
        end_date=None,
        creator_id=None,
        limit=10,
    )
    assert response.summary.total == 0


def test_notification_templates_builds_response(db):
    repo = StubCommunicationRepo()
    service = _service(db, communication_repo=repo)
    response = service.notification_templates()
    assert response.templates
    first = response.templates[0]
    assert "template_id" in first.model_dump()


def test_email_preview_missing_variables(db, monkeypatch):
    _test_email_log.clear()
    service = _service(db)
    response = service.email_preview(
        template="email/auth/password_reset.html",
        variables={"reset_url": "https://example.com"},
        subject="Preview",
        test_send_to=None,
        actor_id="admin",
    )
    assert response.valid is False
    assert "user_name" in response.missing_variables


def test_email_preview_missing_variables_with_test_send(db):
    _test_email_log.clear()
    service = _service(db)
    response = service.email_preview(
        template="email/auth/password_reset.html",
        variables={"reset_url": "https://example.com"},
        subject=None,
        test_send_to="test@example.com",
        actor_id="admin",
    )
    assert response.valid is False
    assert response.test_send_success is False


def test_email_preview_test_send_success(db):
    _test_email_log.clear()
    email_service = StubEmailService()
    service = _service(db, email_service=email_service)
    response = service.email_preview(
        template="email/auth/password_reset.html",
        variables={"reset_url": "https://example.com", "user_name": "Ada"},
        subject="Preview",
        test_send_to="test@example.com",
        actor_id="admin",
    )
    assert response.valid is True
    assert response.test_send_success is True
    assert email_service.sent


def test_email_preview_test_send_exception(db):
    _test_email_log.clear()
    email_service = StubEmailService(raise_for={"test@example.com"})
    service = _service(db, email_service=email_service)
    response = service.email_preview(
        template="email/auth/password_reset.html",
        variables={"reset_url": "https://example.com", "user_name": "Ada"},
        subject=None,
        test_send_to="test@example.com",
        actor_id="admin",
    )
    assert response.valid is True
    assert response.test_send_success is False


def test_email_preview_unknown_template(db):
    service = _service(db)
    with pytest.raises(ValidationException):
        service.email_preview(
            template="missing-template",
            variables={},
            subject=None,
            test_send_to=None,
            actor_id="admin",
        )


def test_test_email_rate_limit(db):
    _test_email_log.clear()
    service = _service(db)
    for _ in range(10):
        service._check_test_email_limit("admin")
    with pytest.raises(ValidationException):
        service._check_test_email_limit("admin")


def test_decode_confirm_payload_errors(db):
    service = _service(db, confirm_service=StubConfirmService(raise_decode=True))
    with pytest.raises(MCPTokenError):
        service._decode_confirm_payload("token", "admin")

    bad_confirm = StubConfirmService({"payload": []})
    bad_confirm.decode_token = lambda _token: {"payload": []}
    service = _service(db, confirm_service=bad_confirm)
    with pytest.raises(ValidationException):
        service._decode_confirm_payload("token", "admin")


def test_parse_datetime_and_run_async(db, monkeypatch):
    service = _service(db)
    assert service._parse_datetime("not-a-date") is None
    parsed = service._parse_datetime("2026-01-01T00:00:00")
    assert parsed is not None

    async def _coro():
        return 42

    def _boom(_coro):
        raise RuntimeError("loop running")

    monkeypatch.setattr("app.services.communication_admin_service.asyncio.run", _boom)
    assert service._run_async(_coro()) == 42


def test_template_required_variables(db):
    service = _service(db)
    template = NotificationTemplate(
        category="system_updates",
        type="notice",
        title="Title",
        body_template="Hi {user_first_name}",
        url_template="/path/{id}",
        email_template=TemplateRegistry.BOOKING_CONFIRMATION_STUDENT,
        email_subject_template="Hello {user_first_name}",
    )
    required = service._template_required_variables(template)
    assert "id" in required
    template_no_url = NotificationTemplate(
        category="system_updates",
        type="notice",
        title="Title",
        body_template="Hi {user_first_name}",
    )
    required = service._template_required_variables(template_no_url)
    assert "user_first_name" in required
