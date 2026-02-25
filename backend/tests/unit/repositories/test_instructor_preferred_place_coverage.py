"""Unit coverage for InstructorPreferredPlaceRepository – uncovered L20."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.repositories.instructor_preferred_place_repository import (
    InstructorPreferredPlaceRepository,
)


def _make_repo() -> tuple[InstructorPreferredPlaceRepository, MagicMock]:
    mock_db = MagicMock()
    repo = InstructorPreferredPlaceRepository(mock_db)
    return repo, mock_db


class TestListForInstructor:
    """L20: list_for_instructor ordering by kind then position."""

    def test_returns_empty_list(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        repo._build_query = MagicMock(return_value=query)
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = []

        result = repo.list_for_instructor("inst-01")
        assert result == []

    def test_returns_ordered_places(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        place1 = MagicMock(kind="teaching_location", position=0)
        place2 = MagicMock(kind="teaching_location", position=1)
        repo._build_query = MagicMock(return_value=query)
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = [place1, place2]

        result = repo.list_for_instructor("inst-01")
        assert len(result) == 2


class TestListForInstructorAndKind:
    def test_filters_by_kind(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        repo._build_query = MagicMock(return_value=query)
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = []

        result = repo.list_for_instructor_and_kind("inst-01", "teaching_location")
        assert result == []


class TestDeleteForKind:
    def test_returns_zero_when_nothing_deleted(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.delete.return_value = 0

        result = repo.delete_for_kind("inst-01", "favorite_park")
        assert result == 0

    def test_returns_count_when_deleted(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.delete.return_value = 3

        result = repo.delete_for_kind("inst-01", "teaching_location")
        assert result == 3

    def test_returns_zero_for_none(self) -> None:
        repo, mock_db = _make_repo()
        query = MagicMock()
        mock_db.query.return_value = query
        query.filter.return_value = query
        query.delete.return_value = None

        result = repo.delete_for_kind("inst-01", "teaching_location")
        assert result == 0
