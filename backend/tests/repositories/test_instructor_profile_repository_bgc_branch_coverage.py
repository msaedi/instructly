"""Additional BGC/report branch coverage for InstructorProfileRepository."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.exceptions import RepositoryException
from app.core.ulid_helper import generate_ulid
from app.repositories.instructor_profile_repository import InstructorProfileRepository


def _repo(db):
    return InstructorProfileRepository(db)


def _profile_for_user(repo: InstructorProfileRepository, user_id: str):
    profile = repo.get_by_user_id(user_id)
    assert profile is not None
    return profile


def test_report_lookup_and_eta_update_roundtrip(db, test_instructor):
    repo = _repo(db)
    profile = _profile_for_user(repo, test_instructor.id)

    report_id = f"rpt_{generate_ulid()}"
    eta = datetime.now(timezone.utc) + timedelta(days=2)

    profile.bgc_report_id = report_id
    db.flush()

    assert repo.update_eta_by_report_id(report_id, eta) == 1

    by_report = repo.get_by_report_id(report_id)
    assert by_report is not None
    assert by_report.id == profile.id
    assert by_report.bgc_eta == eta


def test_invitation_candidate_updates_and_binding_paths(db, test_instructor):
    repo = _repo(db)
    profile = _profile_for_user(repo, test_instructor.id)

    profile.checkr_invitation_id = f"inv_{generate_ulid()}"
    profile.checkr_candidate_id = f"cand_{generate_ulid()}"
    profile.bgc_env = "sandbox"
    db.flush()

    updated_inv = repo.update_bgc_by_invitation(profile.checkr_invitation_id, status="passed")
    assert updated_inv is not None
    assert updated_inv.bgc_status == "passed"

    updated_cand = repo.update_bgc_by_candidate(profile.checkr_candidate_id, note="candidate-note")
    assert updated_cand is not None
    assert updated_cand.bgc_note == "candidate-note"

    report_id = f"rpt_{generate_ulid()}"
    bound_candidate = repo.bind_report_to_candidate(profile.checkr_candidate_id, report_id, env="sandbox")
    assert bound_candidate == profile.id

    # Bind the same report through invitation path to exercise no-op update branches.
    bound_inv = repo.bind_report_to_invitation(profile.checkr_invitation_id, report_id, env="sandbox")
    assert bound_inv == profile.id


def test_fragment_lookup_encrypt_decrypt_and_consent_windows(db, test_instructor):
    repo = _repo(db)
    profile = _profile_for_user(repo, test_instructor.id)

    assert repo._encrypt_report_id(None) is None
    assert repo._encrypt_report_id("") == ""
    assert repo._decrypt_report_id(None) is None
    assert repo._decrypt_report_id("") == ""

    report_id = "rpt_fragment_target"
    profile.bgc_report_id = report_id
    db.flush()

    ids = repo.find_profile_ids_by_report_fragment("fragment")
    assert profile.id in ids

    consent = repo.record_bgc_consent(
        profile.id,
        consent_version="v1",
        ip_address="127.0.0.1",
    )
    assert consent.id is not None
    assert repo.has_recent_consent(profile.id, timedelta(days=1)) is True


def test_status_setters_live_toggle_and_dispute_lifecycle(db, test_instructor):
    repo = _repo(db)
    profile = _profile_for_user(repo, test_instructor.id)

    now = datetime.now(timezone.utc)
    repo.update_valid_until(profile.id, now + timedelta(days=90))
    repo.set_bgc_invited_at(profile.id, now)
    repo.set_pre_adverse_notice(profile.id, "notice-1", now)
    repo.mark_review_email_sent(profile.id, now)
    repo.set_final_adverse_sent_at(profile.id, now)
    repo.set_dispute_open(profile.id, "open-note")
    repo.set_dispute_resolved(profile.id, "resolved-note")
    repo.set_live(profile.id, True)

    refreshed = repo.get_by_id(profile.id)
    assert refreshed is not None
    assert refreshed.bgc_pre_adverse_notice_id == "notice-1"
    assert refreshed.bgc_in_dispute is False
    assert refreshed.is_live is True


def test_update_valid_until_raises_when_profile_missing(db):
    repo = _repo(db)

    with pytest.raises(RepositoryException):
        repo.update_valid_until("01INVALIDPROFILE000000000000", datetime.now(timezone.utc))
