from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.exceptions import RepositoryException, ServiceException
from app.services.background_check_workflow_service import (
    BackgroundCheckWorkflowService,
    _ensure_utc,
)


class TestBackgroundCheckWorkflowCoverage:
    def test_candidate_name_returns_none_without_user(self) -> None:
        service = BackgroundCheckWorkflowService(Mock())
        profile = SimpleNamespace(user=None)

        assert service.candidate_name(profile) is None

    def test_format_date_uses_now_for_none(self) -> None:
        service = BackgroundCheckWorkflowService(Mock())

        formatted = service.format_date(None)

        assert isinstance(formatted, str)
        assert formatted

    def test_ensure_utc_adds_timezone(self) -> None:
        naive = datetime(2025, 1, 1, 12, 0, 0)

        value = _ensure_utc(naive)

        assert value.tzinfo is not None
        assert value.tzinfo.utcoffset(value) is not None

    def test_send_email_skips_without_recipient(self) -> None:
        service = BackgroundCheckWorkflowService(Mock())

        result = service._send_bgc_template_email(
            template=Mock(),
            subject="Subject",
            recipient=None,
            context={},
            suppress=False,
        )

        assert result is False

    def test_send_email_handles_service_exception(self, monkeypatch) -> None:
        service = BackgroundCheckWorkflowService(Mock())

        class FakeSession:
            def __init__(self) -> None:
                self.rolled_back = False
                self.closed = False

            def rollback(self) -> None:
                self.rolled_back = True

            def close(self) -> None:
                self.closed = True

        class FakeTemplateService:
            def __init__(self, _session) -> None:
                pass

            def render_template(self, *_args, **_kwargs):
                raise ServiceException("fail")

        class FakeEmailService:
            def __init__(self, _session) -> None:
                pass

        fake_session = FakeSession()

        monkeypatch.setattr(
            "app.services.background_check_workflow_service.SessionLocal",
            lambda: fake_session,
        )
        monkeypatch.setattr(
            "app.services.background_check_workflow_service.TemplateService",
            FakeTemplateService,
        )
        monkeypatch.setattr(
            "app.services.background_check_workflow_service.EmailService",
            FakeEmailService,
        )

        result = service._send_bgc_template_email(
            template=Mock(),
            subject="Subject",
            recipient="user@example.com",
            context={},
            suppress=False,
        )

        assert result is False
        assert fake_session.rolled_back is True
        assert fake_session.closed is True

    def test_maybe_send_review_status_email_handles_repo_error(self, monkeypatch) -> None:
        class Repo:
            def mark_review_email_sent(self, *_args, **_kwargs):
                raise RepositoryException("boom")

        repo = Repo()
        service = BackgroundCheckWorkflowService(repo)
        profile = SimpleNamespace(id="prof", bgc_review_email_sent_at=None)

        monkeypatch.setattr(service, "send_review_status_email", lambda *_args, **_kwargs: True)

        service._maybe_send_review_status_email(profile, datetime.now(timezone.utc))

        assert profile.bgc_review_email_sent_at is None

    def test_handle_report_suspended_raises_when_missing(self) -> None:
        class Repo:
            def update_bgc_by_report_id(self, *_args, **_kwargs):
                return 0

        service = BackgroundCheckWorkflowService(Repo())

        with pytest.raises(RepositoryException):
            service.handle_report_suspended("report")

    def test_handle_report_completed_bind_flow_missing_profile(self) -> None:
        class Repo:
            def __init__(self) -> None:
                self.calls = 0

            def update_bgc_by_report_id(self, *_args, **_kwargs):
                self.calls += 1
                return 0 if self.calls == 1 else 1

            def bind_report_to_candidate(self, *_args, **_kwargs):
                return "profile"

            def bind_report_to_invitation(self, *_args, **_kwargs):
                return None

            def get_by_report_id(self, *_args, **_kwargs):
                return None

        service = BackgroundCheckWorkflowService(Repo())

        with pytest.raises(RepositoryException):
            service.handle_report_completed(
                report_id="rpt_123",
                result="clear",
                package="standard",
                env="sandbox",
                completed_at=datetime.now(timezone.utc),
            )
