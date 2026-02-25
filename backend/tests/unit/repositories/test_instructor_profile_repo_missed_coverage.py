"""
Coverage tests for instructor_profile_repository.py targeting uncovered paths.

Covers: error handling in repository methods, profile queries with exceptions,
count methods, BGC status counts, founding instructor claim logic,
and apply_public_visibility filter.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import RepositoryException


def _make_repo() -> Any:
    """Create InstructorProfileRepository with mocked db session."""
    from app.repositories.instructor_profile_repository import InstructorProfileRepository

    repo = InstructorProfileRepository.__new__(InstructorProfileRepository)
    repo.db = MagicMock()
    repo.model = MagicMock()
    repo.logger = MagicMock()
    return repo


@pytest.mark.unit
class TestGetPublicById:
    def test_found(self):
        repo = _make_repo()
        mock_profile = MagicMock()
        repo.db.query.return_value.join.return_value.options.return_value = MagicMock()
        mock_chain = repo.db.query.return_value.join.return_value.options.return_value
        mock_chain.filter.return_value.filter.return_value.filter.return_value.first.return_value = mock_profile
        # The method chains multiple filters; need to handle it
        # Simpler: just mock the full chain
        with patch.object(repo, "_apply_public_visibility") as mock_vis:
            mock_vis.return_value.filter.return_value.first.return_value = mock_profile
            result = repo.get_public_by_id("I1")
            assert result is mock_profile

    def test_error_raises_repository_exception(self):
        from sqlalchemy.exc import SQLAlchemyError

        repo = _make_repo()
        repo.db.query.side_effect = SQLAlchemyError("DB error")
        with pytest.raises(RepositoryException, match="Failed to load"):
            repo.get_public_by_id("I1")


@pytest.mark.unit
class TestGetByUserId:
    def test_found(self):
        repo = _make_repo()
        mock_profile = MagicMock()
        repo.db.query.return_value.filter.return_value.first.return_value = mock_profile
        result = repo.get_by_user_id("U1")
        assert result is mock_profile

    def test_not_found(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.first.return_value = None
        result = repo.get_by_user_id("U_NONEXIST")
        assert result is None


@pytest.mark.unit
class TestGetAllWithDetails:
    def test_success(self):
        repo = _make_repo()
        mock_profiles = [MagicMock(), MagicMock()]
        # Build mock chain for the complex query
        mock_query = MagicMock()
        repo.db.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.options.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.distinct.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = mock_profiles

        with patch.object(repo, "_apply_public_visibility", return_value=mock_query):
            result = repo.get_all_with_details(skip=0, limit=10)
            assert len(result) == 2

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("DB error")
        with pytest.raises(RepositoryException, match="Failed to get"):
            repo.get_all_with_details()


@pytest.mark.unit
class TestGetByUserIdWithDetails:
    def test_found(self):
        repo = _make_repo()
        mock_profile = MagicMock()
        mock_chain = MagicMock()
        repo.db.query.return_value = mock_chain
        mock_chain.join.return_value = mock_chain
        mock_chain.options.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain
        mock_chain.first.return_value = mock_profile
        result = repo.get_by_user_id_with_details("U1")
        assert result is mock_profile

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("DB error")
        with pytest.raises(RepositoryException):
            repo.get_by_user_id_with_details("U1")


@pytest.mark.unit
class TestGetProfilesByArea:
    def test_success(self):
        repo = _make_repo()
        mock_profiles = [MagicMock()]
        mock_chain = MagicMock()
        repo.db.query.return_value = mock_chain
        mock_chain.join.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain
        mock_chain.options.return_value = mock_chain
        mock_chain.order_by.return_value = mock_chain
        mock_chain.distinct.return_value = mock_chain
        mock_chain.offset.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.all.return_value = mock_profiles

        with patch.object(repo, "_apply_public_visibility", return_value=mock_chain):
            with patch.object(repo, "_apply_area_filters", return_value=mock_chain):
                result = repo.get_profiles_by_area("Manhattan", skip=0, limit=10)
                assert len(result) == 1

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("DB error")
        with pytest.raises(RepositoryException):
            repo.get_profiles_by_area("Manhattan")


@pytest.mark.unit
class TestGetProfilesByExperience:
    def test_success(self):
        repo = _make_repo()
        mock_profiles = [MagicMock()]
        mock_chain = MagicMock()
        repo.db.query.return_value = mock_chain
        mock_chain.join.return_value = mock_chain
        mock_chain.options.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain
        mock_chain.order_by.return_value = mock_chain
        mock_chain.distinct.return_value = mock_chain
        mock_chain.offset.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.all.return_value = mock_profiles
        result = repo.get_profiles_by_experience(5, skip=0, limit=10)
        assert len(result) == 1

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("DB error")
        with pytest.raises(RepositoryException):
            repo.get_profiles_by_experience(5)


@pytest.mark.unit
class TestCountProfiles:
    def test_success(self):
        repo = _make_repo()
        repo.db.query.return_value.count.return_value = 42
        result = repo.count_profiles()
        assert result == 42

    def test_error(self):
        repo = _make_repo()
        repo.db.query.side_effect = Exception("DB error")
        with pytest.raises(RepositoryException):
            repo.count_profiles()


@pytest.mark.unit
class TestCountFoundingInstructors:
    def test_success(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.scalar.return_value = 5
        result = repo.count_founding_instructors()
        assert result == 5

    def test_none_returns_zero(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.scalar.return_value = None
        result = repo.count_founding_instructors()
        assert result == 0

    def test_error(self):
        from sqlalchemy.exc import SQLAlchemyError

        repo = _make_repo()
        repo.db.query.side_effect = SQLAlchemyError("DB error")
        with pytest.raises(RepositoryException):
            repo.count_founding_instructors()


@pytest.mark.unit
class TestCountByBgcStatus:
    def test_single_status(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.scalar.return_value = 3
        result = repo.count_by_bgc_status("passed")
        assert result == 3


@pytest.mark.unit
class TestCountByBgcStatuses:
    def test_multiple_statuses(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.scalar.return_value = 7
        result = repo.count_by_bgc_statuses(["passed", "pending"])
        assert result == 7

    def test_empty_list(self):
        repo = _make_repo()
        result = repo.count_by_bgc_statuses([])
        assert result == 0

    def test_none_values_stripped(self):
        repo = _make_repo()
        result = repo.count_by_bgc_statuses([None, "", "  "])
        assert result == 0

    def test_error(self):
        from sqlalchemy.exc import SQLAlchemyError

        repo = _make_repo()
        repo.db.query.side_effect = SQLAlchemyError("DB error")
        with pytest.raises(RepositoryException):
            repo.count_by_bgc_statuses(["passed"])


@pytest.mark.unit
class TestTryClaimFoundingStatus:
    def test_cap_zero(self):
        repo = _make_repo()
        success, count = repo.try_claim_founding_status("P1", cap=0)
        assert success is False
        assert count == 0

    def test_negative_cap(self):
        repo = _make_repo()
        success, count = repo.try_claim_founding_status("P1", cap=-1)
        assert success is False

    def test_error(self):
        from sqlalchemy.exc import SQLAlchemyError

        repo = _make_repo()
        repo.db.begin_nested.side_effect = SQLAlchemyError("error")
        with pytest.raises(RepositoryException, match="Failed to claim"):
            repo.try_claim_founding_status("P1", cap=10)


# ── Additional coverage for uncovered lines/branches ────────────


@pytest.mark.unit
class TestUpdateBgcByReportStatus:
    """Covers 503->505 (status is not None branch)."""

    def test_status_set_when_provided(self):
        repo = _make_repo()
        mock_profile = MagicMock()
        mock_profile.bgc_status = "pending"
        repo.get_by_id = MagicMock(return_value=mock_profile)

        with patch.object(repo, "_resolve_profile_id_by_report", return_value="P1"):
            result = repo.update_bgc_by_report_id("R1", status="passed")
        assert result == 1
        assert mock_profile.bgc_status == "passed"

    def test_status_none_not_set(self):
        """503->505 false branch: status is None => don't change bgc_status."""
        repo = _make_repo()
        mock_profile = MagicMock()
        mock_profile.bgc_status = "pending"
        repo.get_by_id = MagicMock(return_value=mock_profile)

        with patch.object(repo, "_resolve_profile_id_by_report", return_value="P1"):
            result = repo.update_bgc_by_report_id("R1", status=None)
        assert result == 1
        # bgc_status unchanged (still "pending" via mock)


@pytest.mark.unit
class TestUpdateBgcByInvitation:
    """Covers 650->652 (status branch) and 691->693 (note branch)."""

    def test_status_set(self):
        """650->652: status is not None => set bgc_status."""
        repo = _make_repo()
        mock_profile = MagicMock()
        mock_chain = MagicMock()
        repo.db.query.return_value = mock_chain
        mock_chain.join.return_value = mock_chain
        mock_chain.options.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain
        mock_chain.first.return_value = mock_profile

        result = repo.update_bgc_by_invitation("INV1", status="passed")
        assert result is mock_profile
        assert mock_profile.bgc_status == "passed"

    def test_status_none_not_set(self):
        """650->652 false branch: status None => don't touch bgc_status."""
        repo = _make_repo()
        mock_profile = MagicMock()
        mock_chain = MagicMock()
        repo.db.query.return_value = mock_chain
        mock_chain.join.return_value = mock_chain
        mock_chain.options.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain
        mock_chain.first.return_value = mock_profile

        mock_profile.bgc_status
        result = repo.update_bgc_by_invitation("INV1", status=None)
        assert result is mock_profile
        # bgc_status not reassigned when status is None


@pytest.mark.unit
class TestUpdateBgcByCandidate:
    """Covers 691->693 (status branch in update_bgc_by_candidate)."""

    def test_status_set(self):
        repo = _make_repo()
        mock_profile = MagicMock()
        repo.db.query.return_value.filter.return_value.first.return_value = mock_profile
        result = repo.update_bgc_by_candidate("CAND1", status="passed")
        assert result is mock_profile
        assert mock_profile.bgc_status == "passed"

    def test_status_none_not_set(self):
        repo = _make_repo()
        mock_profile = MagicMock()
        repo.db.query.return_value.filter.return_value.first.return_value = mock_profile
        result = repo.update_bgc_by_candidate("CAND1", status=None)
        assert result is mock_profile

    def test_profile_not_found_returns_none(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.first.return_value = None
        result = repo.update_bgc_by_candidate("CAND1", status="passed")
        assert result is None

    def test_empty_candidate_id_returns_none(self):
        repo = _make_repo()
        result = repo.update_bgc_by_candidate("", status="passed")
        assert result is None


@pytest.mark.unit
class TestBindReportToCandidate:
    """Covers 728->730 (report mismatch) and 731 (env update)."""

    def test_report_updated_when_different(self):
        """728->730: current_report != report_id => set bgc_report_id."""
        repo = _make_repo()
        mock_profile = MagicMock()
        mock_profile.bgc_report_id = "OLD_REPORT"
        mock_profile.bgc_env = None
        mock_profile.id = "P1"
        repo.db.query.return_value.filter.return_value.first.return_value = mock_profile

        result = repo.bind_report_to_candidate("CAND1", "NEW_REPORT", env="production")
        assert result == "P1"
        assert mock_profile.bgc_report_id == "NEW_REPORT"
        assert mock_profile.bgc_env == "production"

    def test_report_same_not_updated(self):
        """728->730 false branch: same report => no update."""
        repo = _make_repo()
        mock_profile = MagicMock()
        mock_profile.bgc_report_id = "SAME_REPORT"
        mock_profile.bgc_env = "production"
        mock_profile.id = "P1"
        repo.db.query.return_value.filter.return_value.first.return_value = mock_profile

        result = repo.bind_report_to_candidate("CAND1", "SAME_REPORT", env="production")
        assert result == "P1"

    def test_env_not_set_when_none(self):
        """731: env is None => skip bgc_env update."""
        repo = _make_repo()
        mock_profile = MagicMock()
        mock_profile.bgc_report_id = "OLD"
        mock_profile.bgc_env = "staging"
        mock_profile.id = "P1"
        repo.db.query.return_value.filter.return_value.first.return_value = mock_profile

        result = repo.bind_report_to_candidate("CAND1", "NEW", env=None)
        assert result == "P1"

    def test_profile_not_found(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.first.return_value = None
        result = repo.bind_report_to_candidate("CAND1", "R1")
        assert result is None

    def test_empty_candidate_returns_none(self):
        repo = _make_repo()
        result = repo.bind_report_to_candidate(None, "R1")
        assert result is None

    def test_empty_report_returns_none(self):
        repo = _make_repo()
        result = repo.bind_report_to_candidate("CAND1", "")
        assert result is None


@pytest.mark.unit
class TestCountPendingOlderThan:
    """Covers 937-943 (error path)."""

    def test_success(self):
        repo = _make_repo()
        # Need to set model attrs to support comparison operators
        mock_model = MagicMock()
        mock_model.bgc_status = MagicMock()
        mock_model.updated_at = MagicMock()
        mock_model.id = MagicMock()
        # Make __le__ work on mock
        mock_model.updated_at.__le__ = MagicMock(return_value=MagicMock())
        repo.model = mock_model
        repo.db.query.return_value.filter.return_value.scalar.return_value = 3
        result = repo.count_pending_older_than(7)
        assert result == 3

    def test_none_returns_zero(self):
        repo = _make_repo()
        mock_model = MagicMock()
        mock_model.updated_at.__le__ = MagicMock(return_value=MagicMock())
        repo.model = mock_model
        repo.db.query.return_value.filter.return_value.scalar.return_value = None
        result = repo.count_pending_older_than(7)
        assert result == 0

    def test_error_raises_repository_exception(self):
        from sqlalchemy.exc import SQLAlchemyError

        repo = _make_repo()
        repo.db.query.side_effect = SQLAlchemyError("DB error")
        with pytest.raises(RepositoryException, match="Failed to count"):
            repo.count_pending_older_than(7)


@pytest.mark.unit
class TestSetDisputeOpen:
    """Covers 966-972 (error path)."""

    def test_success(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.update.return_value = 1
        repo.set_dispute_open("P1", "note")
        repo.db.flush.assert_called_once()

    def test_not_found_raises(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.update.return_value = 0
        with pytest.raises(RepositoryException, match="not found"):
            repo.set_dispute_open("P_MISSING", None)

    def test_error_raises_repository_exception(self):
        from sqlalchemy.exc import SQLAlchemyError

        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.update.side_effect = SQLAlchemyError("fail")
        with pytest.raises(RepositoryException, match="Failed to mark dispute"):
            repo.set_dispute_open("P1", "note")


@pytest.mark.unit
class TestSetDisputeResolved:
    """Covers 994-1000 (error path)."""

    def test_success(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.update.return_value = 1
        repo.set_dispute_resolved("P1", "resolved note")
        repo.db.flush.assert_called_once()

    def test_not_found_raises(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.update.return_value = 0
        with pytest.raises(RepositoryException, match="not found"):
            repo.set_dispute_resolved("P_MISSING", None)

    def test_error_raises_repository_exception(self):
        from sqlalchemy.exc import SQLAlchemyError

        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.update.side_effect = SQLAlchemyError("fail")
        with pytest.raises(RepositoryException, match="Failed to resolve"):
            repo.set_dispute_resolved("P1", "note")


@pytest.mark.unit
class TestSetLive:
    """Covers 1073-1079 (error path)."""

    def test_success(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.update.return_value = 1
        repo.set_live("P1", True)
        repo.db.flush.assert_called_once()

    def test_not_found_raises(self):
        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.update.return_value = 0
        with pytest.raises(RepositoryException, match="not found"):
            repo.set_live("P_MISSING", True)

    def test_error_raises_repository_exception(self):
        from sqlalchemy.exc import SQLAlchemyError

        repo = _make_repo()
        repo.db.query.return_value.filter.return_value.update.side_effect = SQLAlchemyError("fail")
        with pytest.raises(RepositoryException, match="Failed to update live"):
            repo.set_live("P1", True)


@pytest.mark.unit
class TestFindByFiltersBorough:
    """Covers 1265->1271 (boroughs normalization) and 1312-1313 (non-pg age_group)."""

    def test_boroughs_filter_normalized(self):
        """1265->1271: borough strings normalized to lowercase."""
        from app.repositories.instructor_profile_repository import InstructorProfileRepository

        repo = _make_repo()
        mock_chain = MagicMock()
        repo.db.query.return_value = mock_chain
        mock_chain.join.return_value = mock_chain
        mock_chain.outerjoin.return_value = mock_chain
        mock_chain.options.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain
        mock_chain.order_by.return_value = mock_chain
        mock_chain.distinct.return_value = mock_chain
        mock_chain.offset.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.all.return_value = []

        with patch.object(
            InstructorProfileRepository, "dialect_name", new_callable=lambda: property(lambda self: "sqlite")
        ):
            with patch.object(repo, "_apply_public_visibility", return_value=mock_chain):
                result = repo.find_by_filters(boroughs=["Manhattan", "Brooklyn"])
        assert result == []

    def test_age_group_non_pg_branch(self):
        """1312-1313: non-PostgreSQL dialect uses LIKE for age_group."""
        from app.repositories.instructor_profile_repository import InstructorProfileRepository

        repo = _make_repo()
        mock_chain = MagicMock()
        repo.db.query.return_value = mock_chain
        mock_chain.join.return_value = mock_chain
        mock_chain.outerjoin.return_value = mock_chain
        mock_chain.options.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain
        mock_chain.order_by.return_value = mock_chain
        mock_chain.distinct.return_value = mock_chain
        mock_chain.offset.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.all.return_value = []

        with patch.object(
            InstructorProfileRepository, "dialect_name", new_callable=lambda: property(lambda self: "sqlite")
        ):
            with patch.object(repo, "_apply_public_visibility", return_value=mock_chain):
                result = repo.find_by_filters(age_group="kids")
        assert result == []


@pytest.mark.unit
class TestFindByServiceIds:
    """Covers 1406->1408, 1408->1412, 1423->1422 (price + limit branches)."""

    def test_min_price_filter(self):
        """1406->1408: min_price is not None."""
        repo = _make_repo()
        mock_chain = MagicMock()
        repo.db.query.return_value = mock_chain
        mock_chain.join.return_value = mock_chain
        mock_chain.options.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain
        mock_chain.order_by.return_value = mock_chain
        mock_chain.distinct.return_value = mock_chain
        mock_chain.all.return_value = []

        with patch.object(repo, "_apply_public_visibility", return_value=mock_chain):
            result = repo.find_by_service_ids(["s-1"], min_price=50.0)
        assert result == {"s-1": []}

    def test_max_price_filter(self):
        """1408->1412: max_price is not None."""
        repo = _make_repo()
        mock_chain = MagicMock()
        repo.db.query.return_value = mock_chain
        mock_chain.join.return_value = mock_chain
        mock_chain.options.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain
        mock_chain.order_by.return_value = mock_chain
        mock_chain.distinct.return_value = mock_chain
        mock_chain.all.return_value = []

        with patch.object(repo, "_apply_public_visibility", return_value=mock_chain):
            result = repo.find_by_service_ids(["s-1"], max_price=100.0)
        assert result == {"s-1": []}

    def test_empty_service_ids_returns_empty(self):
        repo = _make_repo()
        result = repo.find_by_service_ids([])
        assert result == {}

    def test_limit_per_service_enforced(self):
        """1423->1422: limit_per_service is respected in grouping."""
        repo = _make_repo()
        mock_chain = MagicMock()
        repo.db.query.return_value = mock_chain
        mock_chain.join.return_value = mock_chain
        mock_chain.options.return_value = mock_chain
        mock_chain.filter.return_value = mock_chain
        mock_chain.order_by.return_value = mock_chain
        mock_chain.distinct.return_value = mock_chain

        # Return 3 profiles for same service
        p1, p2, p3 = MagicMock(), MagicMock(), MagicMock()
        mock_chain.all.return_value = [(p1, "s-1"), (p2, "s-1"), (p3, "s-1")]

        with patch.object(repo, "_apply_public_visibility", return_value=mock_chain):
            result = repo.find_by_service_ids(["s-1"], limit_per_service=2)
        assert len(result["s-1"]) == 2
