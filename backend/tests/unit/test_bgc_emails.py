from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.services.background_check_workflow_service import BackgroundCheckWorkflowService


class DummyRepo:
    def __init__(self, profile):
        self.profile = profile
        self.valid_until = None
        self.pre_notices: list[tuple[str, str, datetime]] = []
        self.review_emails: list[datetime] = []

    def update_bgc_by_report_id(self, report_id, **kwargs):
        self.profile.bgc_status = kwargs.get("status", self.profile.bgc_status)
        self.profile.bgc_completed_at = kwargs.get("completed_at")
        return 1

    def get_by_report_id(self, report_id):
        return self.profile

    def append_history(self, **kwargs):
        return None

    def update_valid_until(self, profile_id, valid_until):
        self.valid_until = valid_until
        self.profile.bgc_valid_until = valid_until

    def set_pre_adverse_notice(self, profile_id, notice_id, sent_at):
        if profile_id != self.profile.id:
            raise AssertionError("Unexpected profile id")
        self.pre_notices.append((notice_id, sent_at))
        self.profile.bgc_pre_adverse_notice_id = notice_id
        self.profile.bgc_pre_adverse_sent_at = sent_at

    def update_eta_by_report_id(self, report_id, eta):
        self.profile.bgc_eta = eta
        return 1

    def mark_review_email_sent(self, profile_id, sent_at):
        if profile_id != self.profile.id:
            raise AssertionError("Unexpected profile id")
        self.review_emails.append(sent_at)
        self.profile.bgc_review_email_sent_at = sent_at

    # Methods for expiry flow hooks
    def count_pending_older_than(self, _days: int) -> int:
        return 0

    def list_expiring_within(self, _days: int, limit: int = 1000):
        return []

    def list_expired(self, limit: int = 1000):
        return []


class FakeSession:
    def __init__(self, profile):
        self.profile = profile
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

    def flush(self):
        return None


class FinalRepo:
    def __init__(self, session):
        self.profile = session.profile

    def get_by_id(self, profile_id, load_relationships=True):
        return self.profile if profile_id == self.profile.id else None

    def set_final_adverse_sent_at(self, profile_id, sent_at):
        self.profile.bgc_final_adverse_sent_at = sent_at

    def record_adverse_event(self, profile_id, notice_id, event_type):
        self.profile.last_adverse_event = (notice_id, event_type)

    def has_adverse_event(self, profile_id, notice_id, event_type):
        return False


@pytest.fixture(autouse=True)
def restore_settings():
    original_suppress = settings.bgc_suppress_adverse_emails
    original_expiry = getattr(settings, "bgc_suppress_expiry_emails", True)
    original_api_key = settings.resend_api_key
    original_from_name = getattr(settings, "email_from_name", None)
    original_from_address = getattr(settings, "email_from_address", None)
    try:
        settings.resend_api_key = "test-key"
        yield
    finally:
        settings.bgc_suppress_adverse_emails = original_suppress
        settings.bgc_suppress_expiry_emails = original_expiry
        settings.resend_api_key = original_api_key
        settings.email_from_name = original_from_name
        settings.email_from_address = original_from_address


def make_profile(**overrides):
    base = {
        "id": "prof_123",
        "bgc_status": "review",
        "bgc_completed_at": None,
        "bgc_valid_until": None,
        "bgc_pre_adverse_notice_id": None,
        "bgc_pre_adverse_sent_at": None,
        "bgc_final_adverse_sent_at": None,
        "bgc_review_email_sent_at": None,
        "bgc_dispute_opened_at": None,
        "bgc_dispute_resolved_at": None,
        "is_live": False,
        "user": SimpleNamespace(email="candidate@example.com", full_name="Candidate Example"),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_review_email_sent_once_when_consider(monkeypatch):
    profile = make_profile()
    repo = DummyRepo(profile)
    service = BackgroundCheckWorkflowService(repo)

    settings.bgc_suppress_adverse_emails = False

    captured_contexts = []

    def fake_send(self, template, subject, recipient, context, suppress, log_extra=None):
        captured_contexts.append((template, subject, recipient, context, suppress))
        return True

    monkeypatch.setattr(
        BackgroundCheckWorkflowService,
        "_send_bgc_template_email",
        fake_send,
        raising=False,
    )

    completed_at = datetime.now(timezone.utc)
    service.handle_report_completed(
        report_id="rpt_123",
        result="consider",
        package="standard",
        env="sandbox",
        completed_at=completed_at,
    )

    assert captured_contexts, "Expected review email to be sent"
    template, subject, recipient, context, suppress = captured_contexts[0]
    from app.services.template_registry import TemplateRegistry

    assert template == TemplateRegistry.BGC_REVIEW_STATUS
    assert "under review" in subject.lower()
    assert recipient == "candidate@example.com"
    assert suppress is False
    assert context["checkr_portal_url"] == settings.checkr_applicant_portal_url
    assert profile.bgc_review_email_sent_at is not None
    assert len(repo.review_emails) == 1

    service.handle_report_completed(
        report_id="rpt_123",
        result="consider",
        package="standard",
        env="sandbox",
        completed_at=completed_at,
    )
    assert len(captured_contexts) == 1


def test_final_adverse_email_called_when_not_in_dispute_and_prod(monkeypatch):
    notice_id = "notice-123"
    profile = make_profile(
        bgc_status="review",
        bgc_pre_adverse_notice_id=notice_id,
        bgc_pre_adverse_sent_at=datetime.now(timezone.utc) - timedelta(days=6),
        bgc_dispute_opened_at=None,
    )

    settings.bgc_suppress_adverse_emails = False

    fake_session = FakeSession(profile)

    monkeypatch.setattr(
        "app.services.background_check_workflow_service.SessionLocal",
        lambda: fake_session,
    )
    monkeypatch.setattr(
        "app.services.background_check_workflow_service.InstructorProfileRepository",
        FinalRepo,
    )

    service = BackgroundCheckWorkflowService(DummyRepo(profile))

    captured_contexts = []

    def fake_send(self, template, subject, recipient, context, suppress, log_extra=None):
        captured_contexts.append((template, subject, recipient, context, suppress))
        return True

    monkeypatch.setattr(
        BackgroundCheckWorkflowService,
        "_send_bgc_template_email",
        fake_send,
        raising=False,
    )

    scheduled_at = datetime.now(timezone.utc)
    result = service._execute_final_adverse_action(profile.id, notice_id, scheduled_at)

    assert result is True
    assert captured_contexts, "Expected final adverse email to be sent"
    from app.services.template_registry import TemplateRegistry

    template, subject, recipient, context, suppress = captured_contexts[0]
    assert template == TemplateRegistry.BGC_FINAL_ADVERSE
    assert "final adverse" in subject.lower()
    assert recipient == "candidate@example.com"
    assert suppress is False
    assert "decision_date" in context
    assert context["candidate_name"] == "Candidate Example"


def test_send_expiry_recheck_email_when_suppression_disabled(monkeypatch):
    profile = make_profile(
        bgc_valid_until=datetime.now(timezone.utc) + timedelta(days=10),
    )
    service = BackgroundCheckWorkflowService(DummyRepo(profile))
    settings.bgc_suppress_expiry_emails = False

    captured = []

    def fake_send(self, template, subject, recipient, context, suppress, log_extra=None):
        captured.append((template, subject, recipient, context, suppress))
        return True

    monkeypatch.setattr(
        BackgroundCheckWorkflowService,
        "_send_bgc_template_email",
        fake_send,
        raising=False,
    )

    context = {
        "candidate_name": "Candidate Example",
        "expiry_date": "September 1, 2025",
        "is_past_due": False,
        "recheck_url": "https://instainstru.com/instructor/onboarding/verification",
        "support_email": "support@example.com",
    }

    service.send_expiry_recheck_email(profile, context)

    from app.services.template_registry import TemplateRegistry

    assert captured
    template, subject, recipient, sent_context, suppress = captured[0]
    assert template == TemplateRegistry.BGC_EXPIRY_RECHECK
    assert recipient == "candidate@example.com"
    assert sent_context == context
    assert suppress is False
