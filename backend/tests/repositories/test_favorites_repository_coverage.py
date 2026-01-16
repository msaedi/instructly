from __future__ import annotations

from unittest.mock import MagicMock

from app.repositories.favorites_repository import FavoritesRepository


class TestFavoritesRepositoryCoverage:
    def test_add_remove_and_counts(self, db, test_student, test_instructor):
        repo = FavoritesRepository(db)

        created = repo.add_favorite(test_student.id, test_instructor.id)
        assert created is not None
        assert repo.is_favorited(test_student.id, test_instructor.id) is True

        # Duplicate should return None
        assert repo.add_favorite(test_student.id, test_instructor.id) is None

        favorites = repo.get_student_favorites(test_student.id)
        assert favorites

        count = repo.get_instructor_favorited_count(test_instructor.id)
        assert count >= 1

        assert repo.remove_favorite(test_student.id, test_instructor.id) is True
        assert repo.remove_favorite(test_student.id, test_instructor.id) is False

        assert repo.is_favorited(test_student.id, test_instructor.id) is False

    def test_get_favorites_with_details(self, db, test_student, test_instructor):
        repo = FavoritesRepository(db)
        repo.add_favorite(test_student.id, test_instructor.id)

        results = repo.get_favorites_with_details(test_student.id)

        assert results
        assert results[0].instructor_profile is not None
        assert results[0].roles is not None

    def test_get_favorite_ids_for_student(self, db, test_student, test_instructor):
        repo = FavoritesRepository(db)
        repo.add_favorite(test_student.id, test_instructor.id)

        ids = repo.get_favorite_ids_for_student(test_student.id)

        assert test_instructor.id in ids

    def test_bulk_check_favorites_error_returns_false(self, db, test_student, test_instructor):
        repo = FavoritesRepository(db)
        repo.add_favorite(test_student.id, test_instructor.id)

        def _boom(_student_id):
            raise RuntimeError("boom")

        repo.get_favorite_ids_for_student = MagicMock(side_effect=_boom)

        result = repo.bulk_check_favorites(test_student.id, [test_instructor.id, "missing"])

        assert result == {test_instructor.id: False, "missing": False}

    def test_error_branches_return_defaults(self):
        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("boom")

        repo = FavoritesRepository(mock_db)
        assert repo.is_favorited("student", "instructor") is False
        assert repo.get_student_favorites("student") == []
        assert repo.get_favorites_with_details("student") == []
        assert repo.get_instructor_favorited_count("instructor") == 0
        assert repo.get_favorite_ids_for_student("student") == []
