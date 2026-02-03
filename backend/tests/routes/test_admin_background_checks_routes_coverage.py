from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.core.exceptions import RepositoryException
from app.models.instructor import InstructorProfile
from app.routes.v1.admin import background_checks as bgc_routes


class _FakeQuery:
    def __init__(self, rows):
        self._rows = list(rows)
        self._offset = 0
        self._limit = None
        self.distinct_called = False
        self.join_called = False

    def filter(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        self.join_called = True
        return self

    def distinct(self):
        self.distinct_called = True
        return self

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, value):
        self._offset = value
        return self

    def limit(self, value):
        self._limit = value
        return self

    def all(self):
        rows = self._rows[self._offset :]
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows

    def count(self):
        return len(self._rows)


class _RepoStub:
    model = InstructorProfile

    def __init__(self, query):
        self._query = query
        self.updated = []
        self.committed = False
        self.rolled_back = False

    def get_bgc_case_base_query(self):
        return self._query

    def find_profile_ids_by_report_fragment(self, term: str):
        return {"profile-1"} if term else set()

    def latest_consent(self, instructor_id: str):
        return None

    def count_by_bgc_statuses(self, statuses):
        return 2

    def count_by_bgc_status(self, status):
        return 1

    def get_history(self, instructor_id: str, *, limit: int, cursor: str | None):
        return []

    def list_expiring_within(self, days: int, *, limit: int):
        return []

    def get_by_report_id(self, report_id: str):
        return SimpleNamespace(id="profile-1")

    def get_by_invitation_id(self, invitation_id: str):
        return SimpleNamespace(id="profile-2")

    def get_by_candidate_id(self, candidate_id: str):
        return SimpleNamespace(id="profile-3")

    def update_bgc(self, *args, **kwargs):
        self.updated.append((args, kwargs))

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def get_by_id(self, instructor_id: str, load_relationships: bool = False):
        return None

    def set_dispute_open(self, instructor_id: str, note: str | None = None):
        return None


def _dummy_request():
    return SimpleNamespace(headers={}, client=None)


def test_parse_event_filters_handles_mappings():
    exact, prefixes = bgc_routes._parse_event_filters(
        ["report.", "error", "custom.", "report.completed"]
    )
    assert "report.completed" in exact
    assert "report.upgrade_failed" in exact
    assert "report." in prefixes
    assert "custom." in prefixes


def test_parse_status_filters_supports_ranges():
    codes = bgc_routes._parse_status_filters(["4xx", "error", "404", "bad"])
    assert 404 in codes
    assert 499 in codes
    assert 500 in codes


def test_extract_payload_object():
    payload = {"data": {"object": {"id": "obj"}}}
    assert bgc_routes._extract_payload_object(payload) == {"id": "obj"}
    assert bgc_routes._extract_payload_object({}) == {}


def test_build_checkr_report_url(monkeypatch):
    monkeypatch.setattr(bgc_routes.settings, "checkr_env", "sandbox")
    assert "sandbox" in bgc_routes._build_checkr_report_url("rpt_1")

    monkeypatch.setattr(bgc_routes.settings, "checkr_env", "production")
    assert "/reports/rpt_2" in bgc_routes._build_checkr_report_url("rpt_2")


def test_build_case_item_handles_consent_and_expiry():
    now = datetime.now(timezone.utc)
    consent = SimpleNamespace(consented_at=now)

    class Repo:
        def latest_consent(self, instructor_id):
            return consent

    profile = SimpleNamespace(
        id="profile-1",
        user=SimpleNamespace(first_name="Jane", last_name="Doe", email="jane@example.com"),
        bgc_report_id="rpt_1",
        bgc_valid_until=now - timedelta(days=1),
        bgc_status="review",
        bgc_includes_canceled=False,
        bgc_completed_at=None,
        created_at=now,
        updated_at=now,
        is_live=True,
        bgc_in_dispute=False,
        bgc_dispute_note=None,
        bgc_dispute_opened_at=None,
        bgc_dispute_resolved_at=None,
        bgc_eta=None,
    )

    item = bgc_routes._build_case_item(profile, Repo(), now)
    assert item.consent_recent is True
    assert item.bgc_is_expired is True


def test_build_case_item_handles_repo_error():
    now = datetime.now(timezone.utc)

    class Repo:
        def latest_consent(self, instructor_id):
            raise RepositoryException("boom")

    profile = SimpleNamespace(
        id="profile-1",
        user=SimpleNamespace(first_name="", last_name="", email=""),
        bgc_report_id=None,
        bgc_valid_until=None,
        bgc_status=None,
        bgc_includes_canceled=False,
        bgc_completed_at=None,
        created_at=None,
        updated_at=None,
        is_live=False,
        bgc_in_dispute=False,
        bgc_dispute_note=None,
        bgc_dispute_opened_at=None,
        bgc_dispute_resolved_at=None,
        bgc_eta=None,
    )

    item = bgc_routes._build_case_item(profile, Repo(), now)
    assert item.consent_recent is False


def test_build_case_query_sets_distinct():
    query = _FakeQuery([])
    repo = _RepoStub(query)
    result = bgc_routes._build_case_query(repo=repo, status="review", search="alice")
    assert result is query
    assert query.distinct_called is True
    assert query.join_called is True


def test_get_bgc_cases_paginated_empty():
    repo = _RepoStub(_FakeQuery([]))
    items, total, current_page, total_pages = bgc_routes._get_bgc_cases_paginated(
        repo=repo,
        status="review",
        page=2,
        page_size=10,
        search=None,
    )
    assert items == []
    assert total == 0
    assert current_page == 1
    assert total_pages == 1


def test_bgc_review_count_and_counts():
    repo = _RepoStub(_FakeQuery([]))
    review = asyncio_run(bgc_routes.bgc_review_count(repo=repo, _=None))
    counts = asyncio_run(bgc_routes.bgc_counts(repo=repo, _=None))

    assert review.count == 2
    assert counts.review == 2
    assert counts.pending == 1


def test_bgc_cases_invalid_status():
    repo = _RepoStub(_FakeQuery([]))
    with pytest.raises(HTTPException) as exc:
        asyncio_run(
            bgc_routes.bgc_cases(
                status_param="bad",
                q=None,
                page=1,
                page_size=10,
                legacy_limit=None,
                repo=repo,
                _=None,
            )
        )
    assert exc.value.status_code == 400


def test_bgc_history_error():
    repo = _RepoStub(_FakeQuery([]))

    def _boom(*_args, **_kwargs):
        raise RepositoryException("history fail")

    repo.get_history = _boom
    with pytest.raises(HTTPException) as exc:
        asyncio_run(
            bgc_routes.bgc_history(
                instructor_id="profile-1", limit=10, cursor=None, repo=repo, _=None
            )
        )
    assert exc.value.status_code == 500


def test_bgc_history_success():
    now = datetime.now(timezone.utc)
    entry = SimpleNamespace(
        id="hist-1",
        result="clear",
        package="basic",
        env="sandbox",
        completed_at=now,
        created_at=now,
        report_id_enc="secret",
    )
    repo = _RepoStub(_FakeQuery([]))
    repo.get_history = lambda *_args, **_kwargs: [entry]
    response = asyncio_run(
        bgc_routes.bgc_history(
            instructor_id="profile-1", limit=10, cursor=None, repo=repo, _=None
        )
    )
    assert response.items[0].id == "hist-1"


def test_bgc_expiring():
    now = datetime.now(timezone.utc)
    profile = SimpleNamespace(id="profile-1", user=SimpleNamespace(email="a@b.com"), bgc_valid_until=now)
    repo = _RepoStub(_FakeQuery([]))
    repo.list_expiring_within = lambda *_args, **_kwargs: [profile]

    items = asyncio_run(bgc_routes.bgc_expiring(days=30, limit=10, repo=repo, _=None))
    assert items[0].instructor_id == "profile-1"


def test_bgc_webhook_logs_and_stats():
    now = datetime.now(timezone.utc)
    entry = SimpleNamespace(
        id="log-1",
        event_type="report.completed",
        delivery_id="deliv",
        resource_id="res",
        http_status=200,
        signature="sig",
        created_at=now,
        payload_json={
            "data": {
                "object": {
                    "object": "report",
                    "id": "rpt_1",
                    "candidate_id": "cand_1",
                    "invitation_id": "inv_1",
                    "result": "clear",
                }
            }
        },
    )

    class LogRepo:
        def list_filtered(self, *args, **kwargs):
            return [entry], None

        def count_errors_since(self, *args, **kwargs):
            return 3

    repo = _RepoStub(_FakeQuery([]))

    response = asyncio_run(
        bgc_routes.bgc_webhook_logs(
            limit=10,
            cursor=None,
            event=[],
            status_param=[],
            q=None,
            log_repo=LogRepo(),
            repo=repo,
            _=None,
        )
    )
    assert response.items[0].instructor_id == "profile-1"
    stats = asyncio_run(bgc_routes.bgc_webhook_stats(log_repo=LogRepo(), _=None))
    assert stats.error_count_24h == 3


def test_bgc_review_override_paths(monkeypatch):
    profile = SimpleNamespace(
        id="profile-1",
        bgc_in_dispute=False,
        bgc_report_id="rpt_1",
        bgc_env=None,
        bgc_completed_at=None,
    )

    repo = _RepoStub(_FakeQuery([]))
    repo.get_by_id = lambda *_args, **_kwargs: profile

    response = asyncio_run(
        bgc_routes.bgc_review_override(
            instructor_id="profile-1",
            request=_dummy_request(),
            payload=bgc_routes.OverridePayload(action="approve"),
            repo=repo,
            _=None,
        )
    )
    assert response.new_status == "passed"
    assert repo.committed is True

    profile.bgc_in_dispute = True
    with pytest.raises(HTTPException) as exc:
        asyncio_run(
            bgc_routes.bgc_review_override(
                instructor_id="profile-1",
                request=_dummy_request(),
                payload=bgc_routes.OverridePayload(action="reject"),
                repo=repo,
                _=None,
            )
        )
    assert exc.value.status_code == 400


def test_bgc_dispute_open_and_resolve(monkeypatch):
    profile = SimpleNamespace(
        id="profile-1",
        bgc_in_dispute=True,
        bgc_dispute_note="note",
        bgc_dispute_opened_at=datetime.now(timezone.utc),
        bgc_dispute_resolved_at=None,
    )
    repo = _RepoStub(_FakeQuery([]))
    repo.get_by_id = lambda *_args, **_kwargs: profile

    response = asyncio_run(
        bgc_routes.open_bgc_dispute(
            instructor_id="profile-1", payload={"note": "note"}, repo=repo, _=None
        )
    )
    assert response.in_dispute is True

    async def _resolve(*_args, **_kwargs):
        return True, None

    monkeypatch.setattr(
        "app.routes.v1.admin.background_checks.BackgroundCheckWorkflowService.resolve_dispute_and_resume_final_adverse",
        lambda *_args, **_kwargs: (True, None),
    )
    resolved = asyncio_run(
        bgc_routes.resolve_bgc_dispute(
            instructor_id="profile-1", payload={"note": "x"}, repo=repo, _=None
        )
    )
    assert resolved.resumed is True


def test_bgc_review_list_and_cases(monkeypatch):
    now = datetime.now(timezone.utc)
    profile = SimpleNamespace(
        id="profile-1",
        user=SimpleNamespace(first_name="Jane", last_name="Doe", email="jane@example.com"),
        bgc_report_id="rpt_1",
        bgc_valid_until=now + timedelta(days=5),
        bgc_status="review",
        bgc_includes_canceled=False,
        bgc_completed_at=None,
        created_at=now,
        updated_at=now,
        is_live=True,
        bgc_in_dispute=False,
        bgc_dispute_note=None,
        bgc_dispute_opened_at=None,
        bgc_dispute_resolved_at=None,
        bgc_eta=None,
    )
    repo = _RepoStub(_FakeQuery([profile]))

    review = asyncio_run(
        bgc_routes.bgc_review_list(limit=10, cursor=None, repo=repo, _=None)
    )
    assert review.items[0].instructor_id == "profile-1"

    cases = asyncio_run(
        bgc_routes.bgc_cases(
            status_param="review",
            q=None,
            page=1,
            page_size=1,
            legacy_limit=None,
            repo=repo,
            _=None,
        )
    )
    assert cases.total == 1
    assert cases.page_size == 1
    assert cases.has_next is False


def test_bgc_cases_uses_legacy_limit():
    now = datetime.now(timezone.utc)
    profile = SimpleNamespace(
        id="profile-1",
        user=SimpleNamespace(first_name="Jane", last_name="Doe", email="jane@example.com"),
        bgc_report_id="rpt_1",
        bgc_valid_until=now + timedelta(days=5),
        bgc_status="review",
        bgc_includes_canceled=False,
        bgc_completed_at=None,
        created_at=now,
        updated_at=now,
        is_live=True,
        bgc_in_dispute=False,
        bgc_dispute_note=None,
        bgc_dispute_opened_at=None,
        bgc_dispute_resolved_at=None,
        bgc_eta=None,
    )
    repo = _RepoStub(_FakeQuery([profile, profile]))
    cases = asyncio_run(
        bgc_routes.bgc_cases(
            status_param="all",
            q=None,
            page=1,
            page_size=1,
            legacy_limit=2,
            repo=repo,
            _=None,
        )
    )
    assert cases.page_size == 2
    assert cases.has_next is False


def test_bgc_review_override_not_found():
    repo = _RepoStub(_FakeQuery([]))
    repo.get_by_id = lambda *_args, **_kwargs: None
    with pytest.raises(HTTPException) as exc:
        asyncio_run(
            bgc_routes.bgc_review_override(
                instructor_id="missing",
                request=_dummy_request(),
                payload=bgc_routes.OverridePayload(action="approve"),
                repo=repo,
                _=None,
            )
        )
    assert exc.value.status_code == 404


def test_bgc_review_override_audit_failure(monkeypatch):
    profile = SimpleNamespace(
        id="profile-1",
        bgc_in_dispute=False,
        bgc_report_id="rpt_1",
        bgc_env=None,
        bgc_completed_at=None,
    )

    repo = _RepoStub(_FakeQuery([]))
    repo.get_by_id = lambda *_args, **_kwargs: profile

    def _boom(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(bgc_routes.AuditService, "log", _boom)

    response = asyncio_run(
        bgc_routes.bgc_review_override(
            instructor_id="profile-1",
            request=_dummy_request(),
            payload=bgc_routes.OverridePayload(action="approve"),
            repo=repo,
            _=None,
        )
    )
    assert response.new_status == "passed"


def test_bgc_dispute_open_handles_repo_error():
    repo = _RepoStub(_FakeQuery([]))

    def _boom(*_args, **_kwargs):
        raise RepositoryException("not found")

    repo.set_dispute_open = _boom
    with pytest.raises(HTTPException) as exc:
        asyncio_run(
            bgc_routes.open_bgc_dispute(
                instructor_id="profile-1", payload={"note": "x"}, repo=repo, _=None
            )
        )
    assert exc.value.status_code == 404


def test_bgc_dispute_resolve_handles_repo_error(monkeypatch):
    repo = _RepoStub(_FakeQuery([]))

    def _boom(*_args, **_kwargs):
        raise RepositoryException("bad")

    monkeypatch.setattr(
        "app.routes.v1.admin.background_checks.BackgroundCheckWorkflowService.resolve_dispute_and_resume_final_adverse",
        _boom,
    )
    with pytest.raises(HTTPException) as exc:
        asyncio_run(
            bgc_routes.resolve_bgc_dispute(
                instructor_id="profile-1", payload={"note": "x"}, repo=repo, _=None
            )
        )
    assert exc.value.status_code == 400


def test_admin_latest_consent_not_found():
    repo = _RepoStub(_FakeQuery([]))
    repo.latest_consent = lambda *_args, **_kwargs: None
    with pytest.raises(HTTPException) as exc:
        asyncio_run(
            bgc_routes.admin_latest_consent(instructor_id="profile-1", repo=repo, _=None)
        )
    assert exc.value.status_code == 404


def asyncio_run(awaitable):
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(awaitable)
    finally:
        loop.close()
