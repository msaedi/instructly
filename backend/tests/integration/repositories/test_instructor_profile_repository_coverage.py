from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time as time_module

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import RepositoryException
from app.models.service_catalog import InstructorService as Service
from app.repositories.factory import RepositoryFactory
from app.repositories.instructor_profile_repository import InstructorProfileRepository


@pytest.fixture
def profile_repo(db):
    return InstructorProfileRepository(db)


def test_founding_and_counts(profile_repo, db, test_instructor, test_instructor_2):
    profile = profile_repo.get_by_user_id(test_instructor.id)
    assert profile is not None

    assert profile_repo.count_profiles() >= 1

    profile.is_founding_instructor = True
    db.commit()

    assert profile_repo.count_founding_instructors() >= 1

    ok, count_after = profile_repo.try_claim_founding_status(profile.id, cap=1)
    assert ok is True
    assert count_after >= 1

    second = profile_repo.get_by_user_id(test_instructor_2.id)
    assert second is not None
    ok2, _ = profile_repo.try_claim_founding_status(second.id, cap=1)
    assert ok2 is False

    assert profile_repo.count_by_bgc_status("passed") >= 1
    assert profile_repo.count_by_bgc_statuses([]) == 0

    joined = profile_repo.get_by_id_join_user(profile.id)
    assert joined is not None
    assert joined.user is not None


def test_bgc_report_updates_and_lookup(profile_repo, db, test_instructor):
    profile = profile_repo.get_by_user_id(test_instructor.id)
    assert profile is not None
    profile.is_live = False
    db.commit()

    profile_repo.update_bgc(
        profile.id,
        status="review",
        report_id="report_123",
        env="sandbox",
        report_result="clear",
        candidate_id="cand_123",
        invitation_id="inv_123",
        note="Initial",
        includes_canceled=False,
    )
    db.commit()
    db.refresh(profile)
    assert profile.checkr_candidate_id == "cand_123"
    assert profile.checkr_invitation_id == "inv_123"

    found = profile_repo.get_by_report_id("report_123")
    assert found is not None
    assert found.id == profile.id

    updated = profile_repo.update_bgc_by_report_id(
        "report_123",
        status="passed",
        completed_at=datetime.now(timezone.utc),
        result="clear",
        note="Done",
        includes_canceled=True,
    )
    assert updated == 1

    eta_rows = profile_repo.update_eta_by_report_id(
        "report_123", eta=datetime.now(timezone.utc) + timedelta(days=2)
    )
    assert eta_rows == 1

    fragment_ids = profile_repo.find_profile_ids_by_report_fragment("report_")
    assert profile.id in fragment_ids


def test_candidate_invitation_bindings(profile_repo, db, test_instructor_2):
    profile = profile_repo.get_by_user_id(test_instructor_2.id)
    assert profile is not None
    profile.is_live = False
    db.commit()

    profile.checkr_candidate_id = "candidate_1"
    profile.checkr_invitation_id = "invite_1"
    db.commit()

    updated_by_candidate = profile_repo.update_bgc_by_candidate(
        "candidate_1", status="review", note="Candidate note"
    )
    assert updated_by_candidate is not None

    updated_by_invite = profile_repo.update_bgc_by_invitation(
        "invite_1", status="review", note="Invite note"
    )
    assert updated_by_invite is not None

    bound_candidate = profile_repo.bind_report_to_candidate(
        "candidate_1", "report_candidate", env="sandbox"
    )
    assert bound_candidate == profile.id

    bound_invite = profile_repo.bind_report_to_invitation(
        "invite_1", "report_invite", env="production"
    )
    assert bound_invite == profile.id

    db.refresh(profile)
    assert profile.bgc_report_id in {"report_candidate", "report_invite"}


def test_bgc_validity_dispute_and_history(profile_repo, db, test_instructor):
    profile = profile_repo.get_by_user_id(test_instructor.id)
    assert profile is not None

    valid_until = datetime.now(timezone.utc) + timedelta(days=10)
    profile_repo.update_valid_until(profile.id, valid_until)
    profile_repo.set_bgc_invited_at(profile.id, datetime.now(timezone.utc))
    profile_repo.set_pre_adverse_notice(profile.id, "notice_1", datetime.now(timezone.utc))
    profile_repo.mark_review_email_sent(profile.id, datetime.now(timezone.utc))
    profile_repo.set_final_adverse_sent_at(profile.id, datetime.now(timezone.utc))

    event_id = profile_repo.record_adverse_event(
        profile.id, "notice_1", "pre_adverse"
    )
    assert event_id
    assert profile_repo.has_adverse_event(profile.id, "notice_1", "pre_adverse") is True

    profile_repo.set_dispute_open(profile.id, "Opened")
    profile_repo.set_dispute_resolved(profile.id, "Resolved")

    history_id = profile_repo.append_history(
        profile.id,
        report_id="history_report",
        result="clear",
        package="standard",
        env="sandbox",
        completed_at=datetime.now(timezone.utc),
    )
    assert history_id

    history = profile_repo.get_history(profile.id, limit=5)
    assert history

    consent = profile_repo.record_bgc_consent(
        profile.id, consent_version="v1", ip_address="127.0.0.1"
    )
    assert consent.id is not None
    assert profile_repo.has_recent_consent(profile.id, timedelta(days=1)) is True

    expiring = profile_repo.list_expiring_within(days=30)
    assert profile.id in [p.id for p in expiring]

    profile.bgc_valid_until = datetime.now(timezone.utc) - timedelta(days=1)
    profile.is_live = True
    profile.bgc_status = "passed"
    db.commit()

    expired = profile_repo.list_expired()
    assert profile.id in [p.id for p in expired]

    profile.is_live = False
    profile.bgc_status = "pending"
    profile.updated_at = datetime.now(timezone.utc) - timedelta(days=10)
    db.commit()
    assert profile_repo.count_pending_older_than(5) >= 1


def test_public_profiles_and_details(profile_repo, db, test_instructor):
    profile = profile_repo.get_by_user_id(test_instructor.id)
    assert profile is not None

    public = profile_repo.get_public_by_id(test_instructor.id)
    assert public is not None

    profile.is_live = False
    db.commit()
    assert profile_repo.get_public_by_id(test_instructor.id) is None

    profile.is_live = True
    db.commit()

    profiles = profile_repo.get_all_with_details(skip=0, limit=5)
    assert profile.id in [p.id for p in profiles]

    with_details = profile_repo.get_by_user_id_with_details(test_instructor.id)
    assert with_details is not None
    assert with_details.user is not None


def test_area_experience_and_filters(profile_repo, db, test_instructor):
    profile = profile_repo.get_by_user_id(test_instructor.id)
    assert profile is not None

    by_area = profile_repo.get_profiles_by_area("Manhattan")
    assert profile.id in [p.id for p in by_area]

    by_experience = profile_repo.get_profiles_by_experience(min_years=1)
    assert profile.id in [p.id for p in by_experience]

    services = list(profile.instructor_services or [])
    assert services
    services[0].age_groups = ["kids", "teens"]
    db.commit()

    service_catalog_id = services[0].service_catalog_id
    filtered = profile_repo.find_by_filters(
        search="Test Instructor",
        service_catalog_id=service_catalog_id,
        min_price=40.0,
        max_price=80.0,
        age_group="kids",
        boroughs=["Manhattan"],
        skip=0,
        limit=10,
    )
    assert profile.id in [p.id for p in filtered]

    batch = profile_repo.find_by_service_ids(
        [service_catalog_id],
        min_price=40.0,
        max_price=80.0,
        limit_per_service=5,
    )
    assert str(service_catalog_id) in batch


def test_invitation_candidate_and_report_helpers(profile_repo, db, test_instructor):
    profile = profile_repo.get_by_user_id(test_instructor.id)
    assert profile is not None

    profile.checkr_invitation_id = "invite_extra"
    profile.checkr_candidate_id = "candidate_extra"
    profile._bgc_report_id = "report_plain"
    db.commit()

    assert profile_repo.get_by_invitation_id("invite_extra") is not None
    assert profile_repo.get_by_candidate_id("candidate_extra") is not None
    assert profile_repo._resolve_profile_id_by_report("report_plain") == profile.id

    encrypted = profile_repo._encrypt_report_id("report_plain")
    assert encrypted is not None
    assert profile_repo._decrypt_report_id(encrypted) is not None

    assert profile.id in profile_repo.find_profile_ids_by_report_fragment("report")

    profile_repo.record_bgc_consent(
        profile.id, consent_version="v2", ip_address="127.0.0.1"
    )
    latest = profile_repo.latest_consent(profile.id)
    assert latest is not None


def test_find_by_filters_age_group_with_boroughs(profile_repo, db, test_instructor):
    profile = profile_repo.get_by_user_id(test_instructor.id)
    assert profile is not None
    services = list(profile.instructor_services or [])
    assert services
    services[0].age_groups = ["adults"]
    db.commit()

    results = profile_repo.find_by_filters(
        age_group="adults", boroughs=[" ", "Manhattan"], limit=5
    )
    assert profile.id in [p.id for p in results]


def test_find_by_service_ids_empty_and_limit(
    profile_repo, db, test_instructor, test_instructor_2
):
    assert profile_repo.find_by_service_ids([]) == {}

    profile = profile_repo.get_by_user_id(test_instructor.id)
    other_profile = profile_repo.get_by_user_id(test_instructor_2.id)
    assert profile is not None and other_profile is not None

    services = list(profile.instructor_services or [])
    assert services
    service_catalog_id = services[0].service_catalog_id

    other_services = list(other_profile.instructor_services or [])
    if not any(s.service_catalog_id == service_catalog_id for s in other_services):
        service_repo = RepositoryFactory.create_base_repository(db, Service)
        service_repo.create(
            instructor_profile_id=other_profile.id,
            service_catalog_id=service_catalog_id,
            hourly_rate=65.0,
            description="Extra",
            duration_options=[60],
        )
        db.commit()

    grouped = profile_repo.find_by_service_ids(
        [service_catalog_id],
        min_price=0,
        max_price=200,
        limit_per_service=1,
    )
    assert len(grouped[str(service_catalog_id)]) <= 1


def test_get_profiles_by_area_blank(profile_repo, test_instructor):
    results = profile_repo.get_profiles_by_area("   ")
    assert test_instructor.id in [p.user_id for p in results]


def test_repo_edge_cases_and_helpers(profile_repo, db, test_instructor):
    profile = profile_repo.get_by_user_id(test_instructor.id)
    assert profile is not None

    assert profile_repo.try_claim_founding_status(profile.id, cap=0) == (False, 0)
    assert profile_repo.get_by_invitation_id("") is None
    assert profile_repo.get_by_candidate_id("") is None
    assert profile_repo.update_bgc_by_invitation("", status="passed") is None
    assert profile_repo.update_bgc_by_candidate("", status="passed") is None
    assert profile_repo.bind_report_to_candidate(None, "report") is None
    assert profile_repo.bind_report_to_invitation(None, "report") is None
    assert profile_repo.find_profile_ids_by_report_fragment("   ") == set()

    base_query = profile_repo.get_bgc_case_base_query()
    assert base_query is not None

    profile_repo.commit()
    profile_repo.rollback()


def test_founding_claim_grants_and_missing_profile(profile_repo, db, test_instructor_2):
    profile = profile_repo.get_by_user_id(test_instructor_2.id)
    assert profile is not None
    profile.is_founding_instructor = False
    db.commit()

    granted, count_after = profile_repo.try_claim_founding_status(profile.id, cap=5)
    assert granted is True
    assert count_after >= 1
    db.refresh(profile)
    assert profile.is_founding_instructor is True

    missing_granted, missing_count = profile_repo.try_claim_founding_status("missing-profile", cap=5)
    assert missing_granted is False
    assert isinstance(missing_count, int)


def test_report_and_invitation_missing_paths(profile_repo, db, test_instructor):
    profile = profile_repo.get_by_user_id(test_instructor.id)
    assert profile is not None
    profile.bgc_report_id = "report_existing"
    profile.checkr_candidate_id = "cand_existing"
    profile.checkr_invitation_id = "inv_existing"
    db.commit()

    assert profile_repo.get_by_report_id("missing_report") is None
    assert profile_repo.update_bgc_by_report_id("missing_report", status="passed") == 0
    assert profile_repo.update_eta_by_report_id("missing_report", eta=None) == 0

    assert profile_repo.get_by_invitation_id("missing_invite") is None
    assert profile_repo.get_by_candidate_id("missing_candidate") is None
    assert profile_repo.update_bgc_by_invitation("missing_invite", status="pending") is None
    assert profile_repo.update_bgc_by_candidate("missing_candidate", status="pending") is None
    assert profile_repo.bind_report_to_candidate("missing_candidate", "report_new") is None
    assert profile_repo.bind_report_to_invitation("missing_invite", "report_new") is None

    profile_repo.set_live(profile.id, False)
    db.refresh(profile)
    assert profile.is_live is False


def test_update_bgc_missing_profile_raises(profile_repo):
    with pytest.raises(RepositoryException):
        profile_repo.update_bgc(
            "missing-profile",
            status="review",
            report_id="report_missing",
            env="sandbox",
        )


def test_update_bgc_by_report_id_missing_profile(profile_repo, monkeypatch):
    monkeypatch.setattr(
        profile_repo, "_resolve_profile_id_by_report", lambda *_args, **_kwargs: "missing-profile"
    )

    assert profile_repo.update_bgc_by_report_id("report_missing", status="passed") == 0
    assert profile_repo.update_eta_by_report_id("report_missing", eta=None) == 0


def test_history_cursor_and_no_consent(profile_repo, db, test_instructor, test_instructor_2):
    profile = profile_repo.get_by_user_id(test_instructor.id)
    assert profile is not None

    first_id = profile_repo.append_history(
        profile.id,
        report_id="history_report_1",
        result="clear",
        package="standard",
        env="sandbox",
        completed_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    second_id = profile_repo.append_history(
        profile.id,
        report_id="history_report_2",
        result="clear",
        package="standard",
        env="sandbox",
        completed_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    assert first_id != second_id

    latest = profile_repo.get_history(profile.id, limit=1)
    assert latest
    older = profile_repo.get_history(profile.id, limit=5, cursor=latest[0].id)
    assert isinstance(older, list)

    other_profile = profile_repo.get_by_user_id(test_instructor_2.id)
    assert other_profile is not None
    assert profile_repo.has_recent_consent(other_profile.id, timedelta(days=1)) is False


def test_report_id_helpers_for_null_and_invalid(profile_repo):
    assert profile_repo._encrypt_report_id(None) is None
    assert profile_repo._decrypt_report_id("v1:bad") == "v1:bad"
    assert profile_repo._resolve_profile_id_by_report(None) is None
    assert profile_repo.find_profile_ids_by_report_fragment("nope") == set()


def test_pre_adverse_notice_missing_profile_raises(profile_repo):
    with pytest.raises(RepositoryException):
        profile_repo.set_pre_adverse_notice("missing", "notice", datetime.now(timezone.utc))
    with pytest.raises(RepositoryException):
        profile_repo.mark_review_email_sent("missing", datetime.now(timezone.utc))
    with pytest.raises(RepositoryException):
        profile_repo.set_final_adverse_sent_at("missing", datetime.now(timezone.utc))


def test_query_error_paths_raise_repository_exception(profile_repo, monkeypatch, test_instructor):
    def _boom(*_args, **_kwargs):
        raise SQLAlchemyError("boom")

    monkeypatch.setattr(profile_repo.db, "query", _boom)

    with pytest.raises(RepositoryException):
        profile_repo.get_public_by_id(test_instructor.id)
    with pytest.raises(RepositoryException):
        profile_repo.get_all_with_details()
    with pytest.raises(RepositoryException):
        profile_repo.get_by_user_id_with_details(test_instructor.id)
    with pytest.raises(RepositoryException):
        profile_repo.get_profiles_by_area("Manhattan")
    with pytest.raises(RepositoryException):
        profile_repo.get_profiles_by_experience(min_years=1)
    with pytest.raises(RepositoryException):
        profile_repo.count_profiles()
    with pytest.raises(RepositoryException):
        profile_repo.count_founding_instructors()
    with pytest.raises(RepositoryException):
        profile_repo.count_by_bgc_statuses(["passed"])
    with pytest.raises(RepositoryException):
        profile_repo.get_by_id_join_user("missing")
    with pytest.raises(RepositoryException):
        profile_repo.get_by_report_id("report")
    with pytest.raises(RepositoryException):
        profile_repo.get_by_invitation_id("invite")
    with pytest.raises(RepositoryException):
        profile_repo.get_by_candidate_id("candidate")
    with pytest.raises(RepositoryException):
        profile_repo.update_bgc_by_invitation("invite", status="pending")
    with pytest.raises(RepositoryException):
        profile_repo.update_bgc_by_candidate("candidate", status="pending")


def test_update_bgc_flush_errors(profile_repo, db, test_instructor, monkeypatch):
    profile = profile_repo.get_by_user_id(test_instructor.id)
    assert profile is not None
    profile.bgc_report_id = "report_error"
    db.commit()

    def _boom(*_args, **_kwargs):
        raise SQLAlchemyError("flush failed")

    monkeypatch.setattr(profile_repo.db, "flush", _boom)

    with pytest.raises(RepositoryException):
        profile_repo.update_bgc(
            profile.id,
            status="review",
            report_id="report_error",
            env="sandbox",
        )
    with pytest.raises(RepositoryException):
        profile_repo.update_bgc_by_report_id("report_error", status="passed")
    with pytest.raises(RepositoryException):
        profile_repo.update_eta_by_report_id("report_error", eta=datetime.now(timezone.utc))


def test_founding_claim_handles_sqlalchemy_error(profile_repo, monkeypatch):
    def _boom(*_args, **_kwargs):
        raise SQLAlchemyError("execute failed")

    monkeypatch.setattr(profile_repo.db, "execute", _boom)
    with pytest.raises(RepositoryException):
        profile_repo.try_claim_founding_status("missing", cap=1)


def test_apply_eager_loading_get_by_id(profile_repo, test_instructor):
    profile = profile_repo.get_by_user_id(test_instructor.id)
    assert profile is not None

    loaded = profile_repo.get_by_id(profile.id, load_relationships=True)
    assert loaded is not None
    assert loaded.user is not None


def test_find_by_filters_logs_slow_query(profile_repo, test_instructor, monkeypatch):
    profile = profile_repo.get_by_user_id(test_instructor.id)
    assert profile is not None

    services = list(profile.instructor_services or [])
    assert services
    service_catalog_id = services[0].service_catalog_id

    calls = {"count": 0}

    def _fake_time() -> float:
        calls["count"] += 1
        return 0.0 if calls["count"] == 1 else 1.0

    monkeypatch.setattr(time_module, "time", _fake_time)

    results = profile_repo.find_by_filters(
        service_catalog_id=service_catalog_id,
        boroughs=["Manhattan"],
        limit=5,
    )
    assert profile.id in [p.id for p in results]


def test_find_by_service_ids_logs_slow_query(profile_repo, test_instructor, monkeypatch):
    profile = profile_repo.get_by_user_id(test_instructor.id)
    assert profile is not None

    services = list(profile.instructor_services or [])
    assert services
    service_catalog_id = services[0].service_catalog_id

    calls = {"count": 0}

    def _fake_time() -> float:
        calls["count"] += 1
        return 0.0 if calls["count"] == 1 else 1.0

    monkeypatch.setattr(time_module, "time", _fake_time)

    results = profile_repo.find_by_service_ids(
        [service_catalog_id],
        min_price=0,
        max_price=200,
        limit_per_service=2,
    )
    assert str(service_catalog_id) in results


def test_decrypt_report_id_empty(profile_repo):
    assert profile_repo._decrypt_report_id("") == ""
