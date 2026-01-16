from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.v1.admin import instructors as routes


class _RepoStub:
    def __init__(self, profile):
        self._profile = profile
        self.db = object()
        self.count = 0

    def get_by_id_join_user(self, instructor_id):
        if self._profile is None:
            return None
        return self._profile if instructor_id == self._profile.id else None

    def latest_consent(self, _profile_id):
        return SimpleNamespace(consented_at=datetime.now(timezone.utc) - timedelta(days=1))

    def count_founding_instructors(self):
        return self.count


@pytest.mark.asyncio
async def test_admin_instructor_detail_missing():
    repo = _RepoStub(None)
    with pytest.raises(Exception) as exc:
        await routes.admin_instructor_detail("missing", repo=repo, _=None)
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_admin_instructor_detail_builds_name_and_expiry():
    now = datetime.now(timezone.utc)
    profile = SimpleNamespace(
        id="profile-1",
        user=SimpleNamespace(first_name="Jane", last_name="Doe", full_name=None, email="j@e.com"),
        is_live=True,
        bgc_status="pending",
        bgc_includes_canceled=False,
        bgc_report_id="rpt-1",
        bgc_completed_at=None,
        created_at=now,
        updated_at=now,
        bgc_valid_until=now - timedelta(days=1),
        bgc_in_dispute=False,
        bgc_dispute_note=None,
        bgc_dispute_opened_at=None,
        bgc_dispute_resolved_at=None,
    )
    repo = _RepoStub(profile)

    response = await routes.admin_instructor_detail("profile-1", repo=repo, _=None)

    assert response.name == "Jane Doe"
    assert response.bgc_is_expired is True
    assert response.bgc_expires_in_days is None


@pytest.mark.asyncio
async def test_founding_instructor_count_parses_cap(monkeypatch):
    repo = _RepoStub(
        SimpleNamespace(id="profile-1", user=None)
    )
    repo.count = 7

    class _ConfigService:
        def __init__(self, _db):
            pass

        def get_pricing_config(self):
            return {"founding_instructor_cap": "bad"}, None

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(routes, "ConfigService", _ConfigService)
    monkeypatch.setattr(routes.asyncio, "to_thread", _to_thread)

    response = await routes.founding_instructor_count(repo=repo, _=None)

    assert response.count == 7
    assert response.cap == 100
    assert response.remaining == 93
