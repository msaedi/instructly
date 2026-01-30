from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.exceptions import RepositoryException
from app.services import background_check_workflow_service as workflow_module
from app.services.background_check_workflow_service import (
    BackgroundCheckWorkflowService,
    _collect_holidays,
)


class TestBackgroundCheckWorkflowService:
    def test_collect_holidays_skips_pre_1900_years(self, monkeypatch) -> None:
        calls: list[int] = []

        def fake_holidays(year: int):
            calls.append(year)
            return set()

        monkeypatch.setattr(workflow_module, "us_federal_holidays", fake_holidays)

        _collect_holidays(datetime(1899, 1, 1, tzinfo=timezone.utc))

        assert calls == [1900]

    def test_handle_report_canceled_binds_via_invitation(self) -> None:
        profile = SimpleNamespace(id="prof-1", bgc_valid_until=None)

        class Repo:
            def __init__(self) -> None:
                self.updated = 0

            def update_bgc_by_report_id(self, *_args, **_kwargs):
                self.updated += 1
                return 0 if self.updated == 1 else 1

            def bind_report_to_candidate(self, *_args, **_kwargs):
                return None

            def bind_report_to_invitation(self, *_args, **_kwargs):
                return "prof-1"

            def get_by_report_id(self, *_args, **_kwargs):
                return profile

            def update_valid_until(self, *_args, **_kwargs):
                return None

            def append_history(self, *_args, **_kwargs):
                return None

        service = BackgroundCheckWorkflowService(Repo())

        result = service.handle_report_canceled(
            report_id="report-1",
            env="sandbox",
            canceled_at=datetime.now(timezone.utc),
            invitation_id="invite-1",
        )

        assert result is profile

    def test_handle_report_canceled_missing_profile_raises(self) -> None:
        class Repo:
            def update_bgc_by_report_id(self, *_args, **_kwargs):
                return 1

            def get_by_report_id(self, *_args, **_kwargs):
                return None

        service = BackgroundCheckWorkflowService(Repo())

        with pytest.raises(RepositoryException):
            service.handle_report_canceled(
                report_id="report-1",
                env="sandbox",
                canceled_at=datetime.now(timezone.utc),
            )

    def test_handle_report_eta_updated_binds_candidate(self) -> None:
        class Repo:
            def __init__(self) -> None:
                self.calls = 0

            def update_eta_by_report_id(self, *_args, **_kwargs):
                self.calls += 1
                return 0 if self.calls == 1 else 1

            def bind_report_to_candidate(self, *_args, **_kwargs):
                return "prof-1"

        service = BackgroundCheckWorkflowService(Repo())

        service.handle_report_eta_updated(
            report_id="report-1",
            env="sandbox",
            eta=datetime.now(timezone.utc),
            candidate_id="cand-1",
        )

    def test_resolve_dispute_missing_profile_raises(self) -> None:
        repo = Mock()
        repo.get_by_id.return_value = None

        service = BackgroundCheckWorkflowService(repo)

        with pytest.raises(RepositoryException):
            service.resolve_dispute_and_resume_final_adverse("prof-1")

    def test_resolve_dispute_not_in_dispute_short_circuits(self) -> None:
        profile = SimpleNamespace(
            id="prof-1",
            bgc_final_adverse_sent_at=None,
            bgc_in_dispute=False,
        )
        repo = Mock(db=Mock())
        repo.get_by_id.return_value = profile

        service = BackgroundCheckWorkflowService(repo)

        result = service.resolve_dispute_and_resume_final_adverse("prof-1")

        repo.set_dispute_resolved.assert_called_once()
        assert result == (False, None)

    def test_resolve_dispute_invalid_status_short_circuits(self) -> None:
        profile = SimpleNamespace(
            id="prof-1",
            bgc_final_adverse_sent_at=None,
            bgc_in_dispute=True,
            bgc_status="passed",
        )
        repo = Mock(db=Mock())
        repo.get_by_id.return_value = profile

        service = BackgroundCheckWorkflowService(repo)

        result = service.resolve_dispute_and_resume_final_adverse("prof-1")

        repo.set_dispute_resolved.assert_called_once()
        assert result == (False, None)

    def test_resolve_dispute_missing_metadata_short_circuits(self) -> None:
        profile = SimpleNamespace(
            id="prof-1",
            bgc_final_adverse_sent_at=None,
            bgc_in_dispute=True,
            bgc_status="review",
            bgc_pre_adverse_sent_at=None,
            bgc_pre_adverse_notice_id=None,
        )
        repo = Mock(db=Mock())
        repo.get_by_id.return_value = profile

        service = BackgroundCheckWorkflowService(repo)

        result = service.resolve_dispute_and_resume_final_adverse("prof-1")

        repo.set_dispute_resolved.assert_called_once()
        assert result == (False, None)

    def test_resolve_dispute_existing_job_immediate(self, monkeypatch) -> None:
        now = datetime.now(timezone.utc)
        profile = SimpleNamespace(
            id="prof-1",
            bgc_final_adverse_sent_at=None,
            bgc_in_dispute=True,
            bgc_status="review",
            bgc_pre_adverse_sent_at=now - timedelta(days=10),
            bgc_pre_adverse_notice_id="notice-1",
        )
        session = Mock()
        existing_job = SimpleNamespace(available_at=None)

        class FakeJobRepo:
            def __init__(self, _session: object) -> None:
                self._session = _session

            def get_pending_final_adverse_job(self, *_args, **_kwargs):
                return existing_job

            def enqueue(self, *_args, **_kwargs):
                raise AssertionError("enqueue should not be called")

        repo = Mock(db=session)
        repo.get_by_id.return_value = profile

        monkeypatch.setattr(workflow_module, "BackgroundJobRepository", FakeJobRepo)

        service = BackgroundCheckWorkflowService(repo)

        enqueued_now, scheduled_for = service.resolve_dispute_and_resume_final_adverse("prof-1")

        assert enqueued_now is True
        assert scheduled_for is None
        session.flush.assert_called_once()
        assert existing_job.available_at is not None

    def test_resolve_dispute_existing_job_scheduled(self, monkeypatch) -> None:
        now = datetime.now(timezone.utc)
        profile = SimpleNamespace(
            id="prof-1",
            bgc_final_adverse_sent_at=None,
            bgc_in_dispute=True,
            bgc_status="review",
            bgc_pre_adverse_sent_at=now,
            bgc_pre_adverse_notice_id="notice-1",
        )
        session = Mock()
        existing_job = SimpleNamespace(available_at=None)

        class FakeJobRepo:
            def __init__(self, _session: object) -> None:
                self._session = _session

            def get_pending_final_adverse_job(self, *_args, **_kwargs):
                return existing_job

            def enqueue(self, *_args, **_kwargs):
                raise AssertionError("enqueue should not be called")

        repo = Mock(db=session)
        repo.get_by_id.return_value = profile

        monkeypatch.setattr(workflow_module, "BackgroundJobRepository", FakeJobRepo)

        service = BackgroundCheckWorkflowService(repo)

        enqueued_now, scheduled_for = service.resolve_dispute_and_resume_final_adverse("prof-1")

        assert enqueued_now is False
        assert scheduled_for is not None
        session.flush.assert_called_once()
        assert existing_job.available_at == scheduled_for

    def test_schedule_final_adverse_action_skips_when_scheduler_disabled(self, monkeypatch) -> None:
        repo = Mock()
        service = BackgroundCheckWorkflowService(repo)

        monkeypatch.setattr(workflow_module.settings, "is_testing", True, raising=False)
        monkeypatch.setattr(workflow_module.settings, "scheduler_enabled", True, raising=False)
        monkeypatch.setattr(
            workflow_module,
            "BackgroundJobRepository",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not create job repo")),
        )

        service._schedule_final_adverse_action("prof-1", notice_id="notice-1", sent_at=datetime.now(timezone.utc))

    def test_schedule_final_adverse_action_missing_profile(self, monkeypatch) -> None:
        class Repo:
            def get_by_id(self, *_args, **_kwargs):
                return None

        repo = Repo()
        service = BackgroundCheckWorkflowService(repo)

        monkeypatch.setattr(workflow_module.settings, "is_testing", False, raising=False)
        monkeypatch.setattr(workflow_module.settings, "scheduler_enabled", True, raising=False)
        monkeypatch.setattr(
            workflow_module,
            "BackgroundJobRepository",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not create job repo")),
        )

        service._schedule_final_adverse_action("prof-1")

    def test_schedule_final_adverse_action_missing_metadata(self, monkeypatch) -> None:
        profile = SimpleNamespace(bgc_pre_adverse_notice_id=None, bgc_pre_adverse_sent_at=None)

        class Repo:
            def get_by_id(self, *_args, **_kwargs):
                return profile

        repo = Repo()
        service = BackgroundCheckWorkflowService(repo)

        monkeypatch.setattr(workflow_module.settings, "is_testing", False, raising=False)
        monkeypatch.setattr(workflow_module.settings, "scheduler_enabled", True, raising=False)
        monkeypatch.setattr(
            workflow_module,
            "BackgroundJobRepository",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not create job repo")),
        )

        service._schedule_final_adverse_action("prof-1")

    def test_execute_final_adverse_action_profile_missing(self, monkeypatch) -> None:
        class FakeRepo:
            def __init__(self, _session: object) -> None:
                pass

            def get_by_id(self, *_args, **_kwargs):
                return None

        class FakeSession:
            def close(self) -> None:
                return None

        monkeypatch.setattr(workflow_module, "InstructorProfileRepository", FakeRepo)
        monkeypatch.setattr(workflow_module, "SessionLocal", lambda: FakeSession())

        service = BackgroundCheckWorkflowService(Mock())

        assert service._execute_final_adverse_action(
            profile_id="prof-1",
            notice_id="notice-1",
            scheduled_at=datetime.now(timezone.utc),
        ) is False

    def test_execute_final_adverse_action_missing_metadata(self, monkeypatch) -> None:
        profile = SimpleNamespace(
            bgc_pre_adverse_notice_id=None,
            bgc_pre_adverse_sent_at=None,
        )

        class FakeRepo:
            def __init__(self, _session: object) -> None:
                self.profile = profile

            def get_by_id(self, *_args, **_kwargs):
                return self.profile

        class FakeSession:
            def close(self) -> None:
                return None

        monkeypatch.setattr(workflow_module, "InstructorProfileRepository", FakeRepo)
        monkeypatch.setattr(workflow_module, "SessionLocal", lambda: FakeSession())

        service = BackgroundCheckWorkflowService(Mock())

        assert service._execute_final_adverse_action(
            profile_id="prof-1",
            notice_id="notice-1",
            scheduled_at=datetime.now(timezone.utc),
        ) is False

    def test_execute_final_adverse_action_skips_live_profile(self, monkeypatch) -> None:
        now = datetime.now(timezone.utc)
        profile = SimpleNamespace(
            bgc_pre_adverse_notice_id="notice-1",
            bgc_pre_adverse_sent_at=now - timedelta(days=10),
            bgc_status="review",
            is_live=True,
            bgc_in_dispute=False,
        )

        class FakeRepo:
            def __init__(self, _session: object) -> None:
                self.profile = profile

            def get_by_id(self, *_args, **_kwargs):
                return self.profile

            def has_adverse_event(self, *_args, **_kwargs):
                return False

        class FakeSession:
            def close(self) -> None:
                return None

        monkeypatch.setattr(workflow_module, "InstructorProfileRepository", FakeRepo)
        monkeypatch.setattr(workflow_module, "SessionLocal", lambda: FakeSession())

        service = BackgroundCheckWorkflowService(Mock())

        assert service._execute_final_adverse_action(
            profile_id="prof-1",
            notice_id="notice-1",
            scheduled_at=now,
        ) is False

    def test_execute_final_adverse_action_skips_dispute_in_flight(self, monkeypatch) -> None:
        now = datetime.now(timezone.utc)
        profile = SimpleNamespace(
            bgc_pre_adverse_notice_id="notice-1",
            bgc_pre_adverse_sent_at=now - timedelta(days=10),
            bgc_status="review",
            is_live=False,
            bgc_in_dispute=False,
            bgc_dispute_opened_at=now - timedelta(days=1),
        )

        class FakeRepo:
            def __init__(self, _session: object) -> None:
                self.profile = profile

            def get_by_id(self, *_args, **_kwargs):
                return self.profile

            def has_adverse_event(self, *_args, **_kwargs):
                return False

        class FakeSession:
            def close(self) -> None:
                return None

        monkeypatch.setattr(workflow_module, "InstructorProfileRepository", FakeRepo)
        monkeypatch.setattr(workflow_module, "SessionLocal", lambda: FakeSession())

        service = BackgroundCheckWorkflowService(Mock())

        assert service._execute_final_adverse_action(
            profile_id="prof-1",
            notice_id="notice-1",
            scheduled_at=now,
        ) is False
