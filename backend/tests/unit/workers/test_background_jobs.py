"""Unit tests for workers/background_jobs.py — covers all extracted helper functions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import NonRetryableError, RepositoryException
from app.workers.background_jobs import (
    _dispatch_known_job,
    _ensure_expiry_job_scheduled,
    _handle_expiry_sweep,
    _handle_final_adverse,
    _handle_report_canceled,
    _handle_report_completed,
    _handle_report_eta,
    _handle_report_suspended,
    _next_expiry_run,
    _normalize_utc_datetime,
    _process_due_jobs,
    _process_single_job,
    _record_non_retryable_failure,
    _record_retryable_failure,
    _required_payload_value,
    _send_recheck_email,
    _update_failed_jobs_gauge,
)

# ---------------------------------------------------------------------------
# _normalize_utc_datetime
# ---------------------------------------------------------------------------


class TestNormalizeUtcDatetime:
    def test_none_returns_none(self) -> None:
        assert _normalize_utc_datetime(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _normalize_utc_datetime("") is None

    def test_datetime_with_tz_converts_to_utc(self) -> None:
        from datetime import timezone as tz

        eastern = tz(timedelta(hours=-5))
        dt = datetime(2024, 6, 15, 12, 0, tzinfo=eastern)
        result = _normalize_utc_datetime(dt)
        assert result is not None
        assert result.tzinfo == timezone.utc
        assert result.hour == 17  # 12 EST = 17 UTC

    def test_naive_datetime_gets_utc(self) -> None:
        dt = datetime(2024, 6, 15, 12, 0)
        result = _normalize_utc_datetime(dt)
        assert result is not None
        assert result.tzinfo == timezone.utc

    def test_iso_string_parsed(self) -> None:
        result = _normalize_utc_datetime("2024-06-15T12:00:00")
        assert result is not None
        assert result.year == 2024
        assert result.tzinfo == timezone.utc

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(RepositoryException, match="Unsupported datetime"):
            _normalize_utc_datetime(12345)


# ---------------------------------------------------------------------------
# _required_payload_value
# ---------------------------------------------------------------------------


class TestRequiredPayloadValue:
    def test_present_value_returned(self) -> None:
        assert _required_payload_value({"key": "val"}, "key", "err") == "val"

    def test_missing_key_raises(self) -> None:
        with pytest.raises(RepositoryException, match="Missing"):
            _required_payload_value({}, "key", "Missing key")

    def test_empty_value_raises(self) -> None:
        with pytest.raises(RepositoryException, match="Empty"):
            _required_payload_value({"key": ""}, "key", "Empty key")


# ---------------------------------------------------------------------------
# _update_failed_jobs_gauge
# ---------------------------------------------------------------------------


class TestUpdateFailedJobsGauge:
    @patch("app.workers.background_jobs.BACKGROUND_JOBS_FAILED")
    def test_sets_gauge_from_repo_count(self, mock_gauge: MagicMock) -> None:
        job_repo = MagicMock()
        job_repo.count_failed_jobs.return_value = 5
        _update_failed_jobs_gauge(job_repo)
        mock_gauge.set.assert_called_once_with(5)


# ---------------------------------------------------------------------------
# _send_recheck_email
# ---------------------------------------------------------------------------


class TestSendRecheckEmail:
    def test_sends_email_with_context(self) -> None:
        workflow = MagicMock()
        workflow.candidate_name.return_value = "John Doe"
        workflow.format_date.return_value = "June 15, 2024"

        profile = SimpleNamespace(bgc_valid_until=datetime(2024, 6, 15, tzinfo=timezone.utc))
        now_utc = datetime(2024, 6, 10, tzinfo=timezone.utc)

        _send_recheck_email(
            workflow, profile, now_utc=now_utc, recheck_url="https://example.com", is_past_due=False,
        )
        workflow.send_expiry_recheck_email.assert_called_once()
        context = workflow.send_expiry_recheck_email.call_args[0][1]
        assert context["candidate_name"] == "John Doe"
        assert context["is_past_due"] is False


# ---------------------------------------------------------------------------
# Handler functions
# ---------------------------------------------------------------------------


class TestHandlers:
    def test_handle_report_completed(self) -> None:
        workflow = MagicMock()
        payload = {"report_id": "rpt-1", "result": "clear", "assessment": "approved"}
        _handle_report_completed(payload, workflow)
        workflow.handle_report_completed.assert_called_once()

    def test_handle_report_suspended(self) -> None:
        workflow = MagicMock()
        _handle_report_suspended({"report_id": "rpt-1"}, workflow)
        workflow.handle_report_suspended.assert_called_once_with("rpt-1")

    def test_handle_report_canceled(self) -> None:
        workflow = MagicMock()
        _handle_report_canceled({"report_id": "rpt-1"}, workflow)
        workflow.handle_report_canceled.assert_called_once()

    def test_handle_report_eta(self) -> None:
        workflow = MagicMock()
        _handle_report_eta({"report_id": "rpt-1", "eta": "2024-06-15T12:00:00"}, workflow)
        workflow.handle_report_eta_updated.assert_called_once()

    def test_handle_final_adverse(self) -> None:
        workflow = MagicMock()
        payload = {"profile_id": "p1", "pre_adverse_notice_id": "n1"}
        scheduled = datetime(2024, 6, 15, tzinfo=timezone.utc)
        _handle_final_adverse(payload, scheduled, workflow)
        workflow.execute_final_adverse_action.assert_called_once_with("p1", "n1", scheduled)


# ---------------------------------------------------------------------------
# _handle_expiry_sweep
# ---------------------------------------------------------------------------


class TestHandleExpirySweep:
    @patch("app.workers.background_jobs.settings")
    def test_disabled_returns_early(self, mock_settings: MagicMock) -> None:
        mock_settings.bgc_expiry_enabled = False
        _handle_expiry_sweep({}, MagicMock(), MagicMock(), MagicMock())

    @patch("app.workers.background_jobs.BGC_PENDING_7D")
    @patch("app.workers.background_jobs.settings")
    def test_enabled_processes_profiles(self, mock_settings: MagicMock, mock_gauge: MagicMock) -> None:
        mock_settings.bgc_expiry_enabled = True
        mock_settings.frontend_url = "https://example.com"
        mock_settings.bgc_support_email = "support@example.com"

        profile_expiring = SimpleNamespace(id="p1", bgc_valid_until=None)
        profile_expired = SimpleNamespace(id="p2", bgc_valid_until=None)

        repo = MagicMock()
        repo.count_pending_older_than.return_value = 3
        repo.list_expiring_within.return_value = [profile_expiring]
        repo.list_expired.return_value = [profile_expired]

        job_repo = MagicMock()
        workflow = MagicMock()
        workflow.candidate_name.return_value = "Test"
        workflow.format_date.return_value = "June 15"

        _handle_expiry_sweep({"days": 30}, job_repo, repo, workflow)

        repo.set_live.assert_called_once_with("p2", False)
        assert workflow.send_expiry_recheck_email.call_count == 2
        job_repo.enqueue.assert_called_once()


# ---------------------------------------------------------------------------
# _dispatch_known_job
# ---------------------------------------------------------------------------


class TestDispatchKnownJob:
    def _make_job(self, job_type: str) -> SimpleNamespace:
        return SimpleNamespace(id="j1", type=job_type, available_at=datetime.now(timezone.utc))

    def test_report_completed(self) -> None:
        workflow = MagicMock()
        job = self._make_job("webhook.report_completed")
        _dispatch_known_job(job, {"report_id": "r1"}, MagicMock(), MagicMock(), workflow)
        workflow.handle_report_completed.assert_called_once()

    def test_report_suspended(self) -> None:
        workflow = MagicMock()
        job = self._make_job("webhook.report_suspended")
        _dispatch_known_job(job, {"report_id": "r1"}, MagicMock(), MagicMock(), workflow)
        workflow.handle_report_suspended.assert_called_once()

    def test_report_canceled(self) -> None:
        workflow = MagicMock()
        job = self._make_job("webhook.report_canceled")
        _dispatch_known_job(job, {"report_id": "r1"}, MagicMock(), MagicMock(), workflow)
        workflow.handle_report_canceled.assert_called_once()

    def test_report_eta(self) -> None:
        workflow = MagicMock()
        job = self._make_job("webhook.report_eta")
        _dispatch_known_job(job, {"report_id": "r1"}, MagicMock(), MagicMock(), workflow)
        workflow.handle_report_eta_updated.assert_called_once()

    @patch("app.workers.background_jobs.FINAL_ADVERSE_JOB_TYPE", "bgc.final_adverse")
    def test_final_adverse(self) -> None:
        workflow = MagicMock()
        job = self._make_job("bgc.final_adverse")
        payload = {"profile_id": "p1", "pre_adverse_notice_id": "n1"}
        _dispatch_known_job(job, payload, MagicMock(), MagicMock(), workflow)
        workflow.execute_final_adverse_action.assert_called_once()

    @patch("app.workers.background_jobs.settings")
    def test_expiry_sweep(self, mock_settings: MagicMock) -> None:
        mock_settings.bgc_expiry_enabled = False
        job = self._make_job("bgc.expiry_sweep")
        _dispatch_known_job(job, {}, MagicMock(), MagicMock(), MagicMock())

    def test_unknown_type_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        job = self._make_job("unknown.type")
        with caplog.at_level("WARNING"):
            _dispatch_known_job(job, {}, MagicMock(), MagicMock(), MagicMock())
        assert "Unknown background job type" in caplog.text


# ---------------------------------------------------------------------------
# Failure recording
# ---------------------------------------------------------------------------


class TestFailureRecording:
    @patch("app.workers.background_jobs.BACKGROUND_JOB_FAILURES_TOTAL")
    @patch("app.workers.background_jobs.BACKGROUND_JOBS_FAILED")
    def test_non_retryable_failure(self, mock_gauge: MagicMock, mock_counter: MagicMock) -> None:
        db = MagicMock()
        job = SimpleNamespace(id="j1", type="webhook.report_completed", attempts=2)
        job_repo = MagicMock()
        exc = NonRetryableError("bad data")

        _record_non_retryable_failure(db, job, job_repo, exc)

        db.rollback.assert_called_once()
        job_repo.mark_terminal_failure.assert_called_once_with("j1", error="bad data")
        db.commit.assert_called_once()

    @patch("app.workers.background_jobs.BACKGROUND_JOB_FAILURES_TOTAL")
    @patch("app.workers.background_jobs.BACKGROUND_JOBS_FAILED")
    def test_retryable_failure_non_terminal(self, mock_gauge: MagicMock, mock_counter: MagicMock) -> None:
        db = MagicMock()
        job = SimpleNamespace(id="j1", type="webhook.report_completed", attempts=1)
        job_repo = MagicMock()
        job_repo.mark_failed.return_value = False  # not terminal

        _record_retryable_failure(db, job, job_repo, Exception("transient"))

        db.rollback.assert_called_once()
        job_repo.mark_failed.assert_called_once()
        db.commit.assert_called_once()

    @patch("app.workers.background_jobs.BACKGROUND_JOB_FAILURES_TOTAL")
    @patch("app.workers.background_jobs.BACKGROUND_JOBS_FAILED")
    def test_retryable_failure_terminal_logs_dead_letter(
        self, mock_gauge: MagicMock, mock_counter: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        db = MagicMock()
        job = SimpleNamespace(id="j1", type="webhook.report_completed", attempts=5)
        job_repo = MagicMock()
        job_repo.mark_failed.return_value = True  # terminal

        with caplog.at_level("ERROR"):
            _record_retryable_failure(db, job, job_repo, Exception("max retries"))

        assert "dead-letter" in caplog.text


# ---------------------------------------------------------------------------
# _process_single_job
# ---------------------------------------------------------------------------


class TestProcessSingleJob:
    @patch("app.workers.background_jobs.process_event", return_value=True)
    @patch("app.workers.background_jobs.BACKGROUND_JOBS_FAILED")
    def test_event_handler_path(self, mock_gauge: MagicMock, mock_process: MagicMock) -> None:
        db = MagicMock()
        job = SimpleNamespace(id="j1", type="some.event", payload={"key": "val"}, attempts=0)
        job_repo = MagicMock()

        _process_single_job(db, job, job_repo, MagicMock(), MagicMock())

        job_repo.mark_running.assert_called_once()
        job_repo.mark_succeeded.assert_called_once()
        db.commit.assert_called()

    @patch("app.workers.background_jobs.process_event", return_value=False)
    @patch("app.workers.background_jobs.BACKGROUND_JOBS_FAILED")
    def test_known_job_path(self, mock_gauge: MagicMock, mock_process: MagicMock) -> None:
        db = MagicMock()
        job = SimpleNamespace(
            id="j1", type="webhook.report_suspended", payload={"report_id": "r1"},
            attempts=0, available_at=None,
        )
        job_repo = MagicMock()
        workflow = MagicMock()

        _process_single_job(db, job, job_repo, MagicMock(), workflow)

        workflow.handle_report_suspended.assert_called_once()
        job_repo.mark_succeeded.assert_called_once()

    @patch("app.workers.background_jobs.process_event", return_value=False)
    @patch("app.workers.background_jobs.BACKGROUND_JOB_FAILURES_TOTAL")
    @patch("app.workers.background_jobs.BACKGROUND_JOBS_FAILED")
    def test_non_retryable_error_caught(
        self, mock_gauge: MagicMock, mock_counter: MagicMock, mock_process: MagicMock
    ) -> None:
        db = MagicMock()
        job = SimpleNamespace(
            id="j1", type="webhook.report_completed",
            payload={"report_id": "r1"},
            attempts=0,
        )
        job_repo = MagicMock()
        workflow = MagicMock()
        workflow.handle_report_completed.side_effect = NonRetryableError("bad data")

        _process_single_job(db, job, job_repo, MagicMock(), workflow)

        job_repo.mark_terminal_failure.assert_called_once()


# ---------------------------------------------------------------------------
# _process_due_jobs
# ---------------------------------------------------------------------------


class TestProcessDueJobs:
    @patch("app.workers.background_jobs.SchedulerSessionLocal")
    def test_no_jobs_commits_and_returns(self, mock_session_cls: MagicMock) -> None:
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        job_repo_instance = MagicMock()
        job_repo_instance.fetch_due.return_value = []

        import threading

        with patch("app.workers.background_jobs.BackgroundJobRepository", return_value=job_repo_instance):
            with patch("app.workers.background_jobs.InstructorProfileRepository"):
                with patch("app.workers.background_jobs.BackgroundCheckWorkflowService"):
                    _process_due_jobs(threading.Event(), batch_size=10)

        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("app.workers.background_jobs.SchedulerSessionLocal")
    @patch("app.workers.background_jobs.process_event", return_value=True)
    @patch("app.workers.background_jobs.BACKGROUND_JOBS_FAILED")
    def test_processes_jobs_and_respects_shutdown(
        self, mock_gauge: MagicMock, mock_process: MagicMock, mock_session_cls: MagicMock
    ) -> None:
        import threading

        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        job = SimpleNamespace(id="j1", type="test.event", payload={}, attempts=0)
        job_repo = MagicMock()
        job_repo.fetch_due.return_value = [job]

        shutdown = threading.Event()
        shutdown.set()  # will break after first check

        with patch("app.workers.background_jobs.BackgroundJobRepository", return_value=job_repo):
            with patch("app.workers.background_jobs.InstructorProfileRepository"):
                with patch("app.workers.background_jobs.BackgroundCheckWorkflowService"):
                    _process_due_jobs(shutdown, batch_size=10)

        mock_db.close.assert_called_once()


# ---------------------------------------------------------------------------
# _ensure_expiry_job_scheduled
# ---------------------------------------------------------------------------


class TestEnsureExpiryJobScheduled:
    @patch("app.workers.background_jobs.settings")
    def test_disabled_returns_early(self, mock_settings: MagicMock) -> None:
        mock_settings.bgc_expiry_enabled = False
        _ensure_expiry_job_scheduled()

    @patch("app.workers.background_jobs.SchedulerSessionLocal")
    @patch("app.workers.background_jobs.settings")
    def test_enabled_no_existing_creates_job(
        self, mock_settings: MagicMock, mock_session_cls: MagicMock
    ) -> None:
        mock_settings.bgc_expiry_enabled = True
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        job_repo = MagicMock()
        job_repo.get_next_scheduled.return_value = None

        with patch("app.workers.background_jobs.BackgroundJobRepository", return_value=job_repo):
            _ensure_expiry_job_scheduled()

        job_repo.enqueue.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("app.workers.background_jobs.SchedulerSessionLocal")
    @patch("app.workers.background_jobs.settings")
    def test_enabled_existing_job_skips_create(
        self, mock_settings: MagicMock, mock_session_cls: MagicMock
    ) -> None:
        mock_settings.bgc_expiry_enabled = True
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        job_repo = MagicMock()
        job_repo.get_next_scheduled.return_value = SimpleNamespace(id="existing")

        with patch("app.workers.background_jobs.BackgroundJobRepository", return_value=job_repo):
            _ensure_expiry_job_scheduled()

        job_repo.enqueue.assert_not_called()
        mock_db.commit.assert_called_once()


# ---------------------------------------------------------------------------
# _next_expiry_run
# ---------------------------------------------------------------------------


class TestNextExpiryRun:
    def test_before_3am_returns_today_3am(self) -> None:
        now = datetime(2024, 6, 15, 1, 0, tzinfo=timezone.utc)
        result = _next_expiry_run(now)
        assert result.hour == 3
        assert result.day == 15

    def test_after_3am_returns_tomorrow_3am(self) -> None:
        now = datetime(2024, 6, 15, 4, 0, tzinfo=timezone.utc)
        result = _next_expiry_run(now)
        assert result.hour == 3
        assert result.day == 16
