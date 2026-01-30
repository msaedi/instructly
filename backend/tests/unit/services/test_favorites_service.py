"""Unit tests for FavoritesService."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.core.exceptions import NotFoundException, ValidationException
from app.services.favorites_service import FavoritesService


class _Role:
    def __init__(self, name: str):
        self.name = name


class _Cache:
    def __init__(self, value=None):
        self.value = value
        self.deleted: list[str] = []

    def get(self, key: str):
        return self.value

    def set(self, key: str, value, ttl=None):
        return True

    def delete(self, key: str):
        self.deleted.append(key)
        return True


@pytest.fixture
def service():
    repo = Mock()
    user_repo = Mock()
    return FavoritesService(db=Mock(), favorites_repository=repo, user_repository=user_repo)


class TestFavoritesService:
    def test_add_favorite_repository_error(self, service):
        service._validate_student = Mock(return_value=SimpleNamespace())
        service._validate_instructor = Mock(return_value=SimpleNamespace())
        service.favorites_repository.add_favorite.side_effect = Exception("boom")

        with pytest.raises(ValidationException):
            service.add_favorite("student-1", "instructor-1")

    def test_remove_favorite_repository_error(self, service):
        service._validate_student = Mock(return_value=SimpleNamespace())
        service._validate_instructor = Mock(return_value=SimpleNamespace())
        service.favorites_repository.remove_favorite.side_effect = Exception("boom")

        with pytest.raises(ValidationException):
            service.remove_favorite("student-1", "instructor-1")

    def test_is_favorited_cached_str(self, service):
        service.cache = _Cache(value="1")

        assert service.is_favorited("student-1", "instructor-1") is True

    def test_bulk_check_favorites_guest(self, service):
        results = service.bulk_check_favorites("", ["i1", "i2"])

        assert results == {"i1": False, "i2": False}

    def test_validate_student_not_found(self, service):
        service.user_repository.get_with_roles.return_value = None

        with pytest.raises(NotFoundException):
            service._validate_student("student-1")

    def test_validate_student_not_student(self, service):
        service.user_repository.get_with_roles.return_value = SimpleNamespace(roles=[_Role("coach")])

        with pytest.raises(ValidationException):
            service._validate_student("student-1")

    def test_validate_instructor_not_instructor(self, service):
        service.user_repository.get_instructor.return_value = None
        service.user_repository.get_by_id.return_value = SimpleNamespace()

        with pytest.raises(ValidationException):
            service._validate_instructor("instructor-1")

    def test_validate_instructor_not_found(self, service):
        service.user_repository.get_instructor.return_value = None
        service.user_repository.get_by_id.return_value = None

        with pytest.raises(NotFoundException):
            service._validate_instructor("instructor-1")
