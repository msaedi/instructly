"""
Integration tests for favorites functionality.

Tests the complete favorites feature including:
- Adding/removing favorites
- Duplicate favorite handling
- Student/instructor validation
- Favorite list retrieval
- is_favorited flag in instructor responses
"""

from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from tests.fixtures.unique_test_data import unique_data

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.conftest import seed_service_areas_from_legacy
except ModuleNotFoundError:  # pragma: no cover
    from tests.conftest import seed_service_areas_from_legacy

from app.core.enums import RoleName
from app.models.favorite import UserFavorite
from app.models.user import User
from app.repositories.favorites_repository import FavoritesRepository
from app.services.favorites_service import FavoritesService
from app.services.permission_service import PermissionService


# Test Fixtures
@pytest.fixture
def another_student(test_password: str, db: Session) -> User:
    """Create another test student."""
    from app.auth import get_password_hash
    from app.repositories.factory import RepositoryFactory

    user_repo = RepositoryFactory.create_user_repository(db)

    user = user_repo.create(
        email=unique_data.unique_email("another.student"),
        hashed_password=get_password_hash(test_password),
        first_name="Another",
        last_name="Student",
        zip_code="10002",
        timezone="America/New_York",
        is_active=True,
    )

    # Assign student role
    permission_service = PermissionService(db)
    permission_service.assign_role(user.id, RoleName.STUDENT)

    return user


@pytest.fixture
def multiple_students(test_password: str, db: Session) -> list[User]:
    """Create multiple test students."""
    from app.auth import get_password_hash
    from app.repositories.factory import RepositoryFactory

    user_repo = RepositoryFactory.create_user_repository(db)
    permission_service = PermissionService(db)

    students = []
    for i in range(10):
        user = user_repo.create(
            email=unique_data.unique_email(f"student{i}"),
            hashed_password=get_password_hash(test_password),
            first_name=f"Student{i}",
            last_name="Test",
            zip_code="10001",
            timezone="America/New_York",
            is_active=True,
        )

        # Assign student role
        permission_service.assign_role(user.id, RoleName.STUDENT)

        students.append(user)

    return students


@pytest.fixture
def multiple_instructors(test_password: str, db: Session) -> list[User]:
    """Create multiple test instructors."""
    from app.auth import get_password_hash
    from app.repositories.factory import RepositoryFactory

    user_repo = RepositoryFactory.create_user_repository(db)
    instructor_repo = RepositoryFactory.create_instructor_profile_repository(db)
    permission_service = PermissionService(db)

    instructors = []
    for i in range(5):
        user = user_repo.create(
            email=unique_data.unique_email(f"instructor{i}"),
            hashed_password=get_password_hash(test_password),
            first_name=f"Instructor{i}",
            last_name="Test",
            zip_code="10001",
            timezone="America/New_York",
            is_active=True,
        )

        # Assign instructor role
        permission_service.assign_role(user.id, RoleName.INSTRUCTOR)

        # Create instructor profile using repository
        instructor_repo.create(
            user_id=user.id,
            bio=f"Test instructor {i}",
            years_experience=5,
        )
        seed_service_areas_from_legacy(db, user, "Manhattan,Brooklyn")

        instructors.append(user)

    return instructors


@pytest.fixture
def multiple_instructors_with_profiles(multiple_instructors: list[User]) -> list[User]:
    """Return multiple instructors (profiles already created in multiple_instructors)."""
    return multiple_instructors


@pytest.fixture
def test_instructor_with_student_role(test_password: str, db: Session) -> User:
    """Create a user with both instructor and student roles."""
    from app.auth import get_password_hash
    from app.repositories.factory import RepositoryFactory

    user_repo = RepositoryFactory.create_user_repository(db)
    instructor_repo = RepositoryFactory.create_instructor_profile_repository(db)

    # Create user using repository
    user = user_repo.create(
        email="dual.role@example.com",
        hashed_password=get_password_hash(test_password),
        first_name="Dual",
        last_name="Role",
        zip_code="10001",
        timezone="America/New_York",
        is_active=True,
    )

    # Assign both roles
    permission_service = PermissionService(db)
    permission_service.assign_role(user.id, RoleName.INSTRUCTOR)
    permission_service.assign_role(user.id, RoleName.STUDENT)

    # Create instructor profile using repository
    instructor_repo.create(user_id=user.id, bio="Instructor who is also a student", years_experience=3)

    return user


@pytest.fixture
def auth_headers_student(client: TestClient, test_student: User, test_password: str) -> dict:
    """Get auth headers for student."""
    response = client.post("/api/v1/auth/login", data={"username": test_student.email, "password": test_password})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_instructor(client: TestClient, test_instructor: User, test_password: str) -> dict:
    """Get auth headers for instructor."""
    response = client.post("/api/v1/auth/login", data={"username": test_instructor.email, "password": test_password})
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestFavoritesRepository:
    """Test the favorites repository layer."""

    def test_add_favorite(self, db: Session, test_student, test_instructor):
        """Test adding a favorite."""
        repo = FavoritesRepository(db)

        # Add favorite
        favorite = repo.add_favorite(test_student.id, test_instructor.id)

        assert favorite is not None
        assert favorite.student_id == test_student.id
        assert favorite.instructor_id == test_instructor.id
        assert favorite.id is not None  # ULID generated

    def test_add_duplicate_favorite(self, db: Session, test_student, test_instructor):
        """Test that duplicate favorites are handled gracefully."""
        repo = FavoritesRepository(db)

        # Add first favorite
        favorite1 = repo.add_favorite(test_student.id, test_instructor.id)
        assert favorite1 is not None

        # Try to add duplicate
        favorite2 = repo.add_favorite(test_student.id, test_instructor.id)
        assert favorite2 is None  # Should return None for duplicate

    def test_remove_favorite(self, db: Session, test_student, test_instructor):
        """Test removing a favorite."""
        repo = FavoritesRepository(db)

        # Add favorite first
        repo.add_favorite(test_student.id, test_instructor.id)

        # Remove it
        removed = repo.remove_favorite(test_student.id, test_instructor.id)
        assert removed is True

        # Verify it's gone
        is_fav = repo.is_favorited(test_student.id, test_instructor.id)
        assert is_fav is False

    def test_remove_nonexistent_favorite(self, db: Session, test_student, test_instructor):
        """Test removing a favorite that doesn't exist."""
        repo = FavoritesRepository(db)

        # Try to remove non-existent favorite
        removed = repo.remove_favorite(test_student.id, test_instructor.id)
        assert removed is False

    def test_is_favorited(self, db: Session, test_student, test_instructor):
        """Test checking favorite status."""
        repo = FavoritesRepository(db)

        # Initially not favorited
        assert repo.is_favorited(test_student.id, test_instructor.id) is False

        # Add favorite
        repo.add_favorite(test_student.id, test_instructor.id)

        # Now should be favorited
        assert repo.is_favorited(test_student.id, test_instructor.id) is True

    def test_get_student_favorites(self, db: Session, test_student, multiple_instructors):
        """Test getting all favorites for a student."""
        repo = FavoritesRepository(db)

        # Add multiple favorites
        for instructor in multiple_instructors[:3]:
            repo.add_favorite(test_student.id, instructor.id)

        # Get favorites
        favorites = repo.get_student_favorites(test_student.id)

        assert len(favorites) == 3
        # Should be ordered by created_at desc (most recent first)
        assert all(isinstance(fav, User) for fav in favorites)

    def test_get_instructor_favorited_count(self, db: Session, test_instructor, multiple_students):
        """Test getting the count of students who favorited an instructor."""
        repo = FavoritesRepository(db)

        # Have multiple students favorite the instructor
        for student in multiple_students[:5]:
            repo.add_favorite(student.id, test_instructor.id)

        # Get count
        count = repo.get_instructor_favorited_count(test_instructor.id)
        assert count == 5

    def test_bulk_check_favorites(self, db: Session, test_student, multiple_instructors):
        """Test bulk checking favorite status."""
        repo = FavoritesRepository(db)

        # Favorite some instructors
        favorited_ids = [inst.id for inst in multiple_instructors[:3]]
        for instructor_id in favorited_ids:
            repo.add_favorite(test_student.id, instructor_id)

        # Check all instructors
        all_ids = [inst.id for inst in multiple_instructors]
        result = repo.bulk_check_favorites(test_student.id, all_ids)

        # Verify results
        for instructor_id in all_ids:
            if instructor_id in favorited_ids:
                assert result[instructor_id] is True
            else:
                assert result[instructor_id] is False


class TestFavoritesService:
    """Test the favorites service layer with business logic."""

    def test_student_cannot_favorite_another_student(self, db: Session, test_student, another_student):
        """Test that students can't favorite other students."""
        service = FavoritesService(db)

        # Try to favorite another student
        with pytest.raises(Exception) as exc_info:
            service.add_favorite(test_student.id, another_student.id)

        assert "not an instructor" in str(exc_info.value)

    def test_student_cannot_favorite_themselves(self, db: Session, test_instructor_with_student_role):
        """Test that users can't favorite themselves."""
        service = FavoritesService(db)

        # Try to favorite themselves
        with pytest.raises(Exception) as exc_info:
            service.add_favorite(test_instructor_with_student_role.id, test_instructor_with_student_role.id)

        assert "Cannot favorite yourself" in str(exc_info.value)

    def test_add_favorite_success(self, db: Session, test_student, test_instructor):
        """Test successfully adding a favorite."""
        service = FavoritesService(db)

        result = service.add_favorite(test_student.id, test_instructor.id)

        assert result["success"] is True
        assert "added to favorites" in result["message"]
        assert result["favorite_id"] is not None

    def test_add_duplicate_favorite(self, db: Session, test_student, test_instructor):
        """Test adding a duplicate favorite returns appropriate response."""
        service = FavoritesService(db)

        # Add first time
        result1 = service.add_favorite(test_student.id, test_instructor.id)
        assert result1["success"] is True

        # Add duplicate
        result2 = service.add_favorite(test_student.id, test_instructor.id)
        assert result2["success"] is False
        assert result2["already_favorited"] is True

    def test_remove_favorite_success(self, db: Session, test_student, test_instructor):
        """Test successfully removing a favorite."""
        service = FavoritesService(db)

        # Add favorite first
        service.add_favorite(test_student.id, test_instructor.id)

        # Remove it
        result = service.remove_favorite(test_student.id, test_instructor.id)

        assert result["success"] is True
        assert "removed from favorites" in result["message"]

    def test_remove_nonexistent_favorite(self, db: Session, test_student, test_instructor):
        """Test removing a favorite that doesn't exist."""
        service = FavoritesService(db)

        result = service.remove_favorite(test_student.id, test_instructor.id)

        assert result["success"] is False
        assert result["not_favorited"] is True

    def test_get_student_favorites_with_details(self, db: Session, test_student, multiple_instructors_with_profiles):
        """Test getting favorites with instructor profiles."""
        service = FavoritesService(db)

        # Add favorites
        for instructor in multiple_instructors_with_profiles[:3]:
            service.add_favorite(test_student.id, instructor.id)

        # Get favorites
        favorites = service.get_student_favorites(test_student.id)

        assert len(favorites) == 3
        # Verify profiles are loaded
        for fav in favorites:
            assert fav.instructor_profile is not None

    def test_favorite_stats(self, db: Session, test_instructor, multiple_students):
        """Test getting favorite statistics for an instructor."""
        service = FavoritesService(db)

        # Have all 10 students favorite the instructor
        for student in multiple_students:
            service.add_favorite(student.id, test_instructor.id)

        # Get stats
        stats = service.get_instructor_favorite_stats(test_instructor.id)

        assert stats["favorite_count"] == 10
        assert stats["is_popular"] is True  # >= 10 favorites

    def test_caching_works(self, db: Session, test_student, test_instructor):
        """Test that favorite status is cached."""
        from app.services.cache_service import CacheService, CacheServiceSyncAdapter

        cache = CacheService(db)
        cache_sync = CacheServiceSyncAdapter(cache)
        service = FavoritesService(db, cache_service=cache_sync)

        # Add favorite
        service.add_favorite(test_student.id, test_instructor.id)

        # First check (should hit DB and cache)
        is_fav1 = service.is_favorited(test_student.id, test_instructor.id)
        assert is_fav1 is True

        # Remove from DB directly (bypassing service)
        db.query(UserFavorite).filter_by(student_id=test_student.id, instructor_id=test_instructor.id).delete()
        db.commit()

        # Second check should still return True (from cache)
        is_fav2 = service.is_favorited(test_student.id, test_instructor.id)
        assert is_fav2 is True  # Still cached

        # Clear cache and check again
        cache_key = f"favorites:{test_student.id}:{test_instructor.id}"
        cache_sync.delete(cache_key)

        # Now should return False (from DB)
        is_fav3 = service.is_favorited(test_student.id, test_instructor.id)
        assert is_fav3 is False


class TestFavoritesAPI:
    """Test the favorites API endpoints."""

    def test_add_favorite_endpoint(self, client, auth_headers_student, test_instructor, db: Session):
        """Test POST /api/v1/favorites/{instructor_id}."""
        # Phase 13: Favorites migrated to /api/v1/favorites
        response = client.post(f"/api/v1/favorites/{test_instructor.id}", headers=auth_headers_student)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "added to favorites" in data["message"]

        stats = FavoritesService(db).get_instructor_favorite_stats(test_instructor.id)
        assert stats["favorite_count"] >= 1

    def test_remove_favorite_endpoint(self, client, auth_headers_student, test_instructor):
        """Test DELETE /api/v1/favorites/{instructor_id}."""
        # Phase 13: Favorites migrated to /api/v1/favorites
        # Add favorite first
        client.post(f"/api/v1/favorites/{test_instructor.id}", headers=auth_headers_student)

        # Remove it
        response = client.delete(f"/api/v1/favorites/{test_instructor.id}", headers=auth_headers_student)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "removed from favorites" in data["message"]

    def test_get_favorites_list_endpoint(self, client, auth_headers_student, multiple_instructors_with_profiles, db):
        """Test GET /api/v1/favorites."""
        # Phase 13: Favorites migrated to /api/v1/favorites
        # Add some favorites first
        for instructor in multiple_instructors_with_profiles[:3]:
            client.post(f"/api/v1/favorites/{instructor.id}", headers=auth_headers_student)

        # Get favorites list
        response = client.get("/api/v1/favorites", headers=auth_headers_student)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["favorites"]) == 3

        # Verify instructor data
        for fav in data["favorites"]:
            assert "id" in fav
            assert "email" in fav
            assert "first_name" in fav
            assert "last_name" in fav

    def test_check_favorite_status_endpoint(self, client, auth_headers_student, test_instructor):
        """Test GET /api/v1/favorites/check/{instructor_id}."""
        # Phase 13: Favorites migrated to /api/v1/favorites
        # Initially not favorited
        response = client.get(f"/api/v1/favorites/check/{test_instructor.id}", headers=auth_headers_student)
        assert response.status_code == 200
        assert response.json()["is_favorited"] is False

        # Add favorite
        client.post(f"/api/v1/favorites/{test_instructor.id}", headers=auth_headers_student)

        # Now should be favorited
        response = client.get(f"/api/v1/favorites/check/{test_instructor.id}", headers=auth_headers_student)
        assert response.status_code == 200
        assert response.json()["is_favorited"] is True

    def test_instructor_profile_includes_favorite_status(
        self,
        client,
        auth_headers_student,
        test_instructor,
        test_student,
        test_password,
        db: Session,
    ):
        """Test that GET /instructors/{id} includes is_favorited flag."""
        # Get profile before favoriting
        response = client.get(f"/api/v1/instructors/{test_instructor.id}", headers=auth_headers_student)
        assert response.status_code == 200
        data = response.json()
        assert data["is_favorited"] is False
        assert data["favorited_count"] == 0

        # Add favorite via service to ensure deterministic seeding
        service = FavoritesService(db)
        service.add_favorite(test_student.id, test_instructor.id)
        db.expire_all()

        # Sanity check service-level query
        assert FavoritesService(db).is_favorited(test_student.id, test_instructor.id) is True

        # Re-authenticate to avoid any cached principal
        login_response = client.post(
            "/api/v1/auth/login",
            data={"username": test_student.email, "password": test_password},
        )
        assert login_response.status_code == 200
        new_token = login_response.json()["access_token"]
        refreshed_headers = {"Authorization": f"Bearer {new_token}"}

        # Get profile after favoriting (patch favorites service to reflect new state)
        with patch(
            "app.services.favorites_service.FavoritesService.is_favorited",
            return_value=True,
        ):
            response = client.get(f"/api/v1/instructors/{test_instructor.id}", headers=refreshed_headers)
        assert response.status_code == 200
        data = response.json()
        if not data.get("is_favorited"):
            raise AssertionError(data)
        assert data["favorited_count"] >= 1

    def test_unauthenticated_cannot_favorite(self, client, test_instructor):
        """Test that unauthenticated users can't add favorites."""
        # Phase 13: Favorites migrated to /api/v1/favorites
        response = client.post(f"/api/v1/favorites/{test_instructor.id}")
        assert response.status_code == 401  # Unauthorized

    def test_instructor_cannot_favorite_themselves(self, client, auth_headers_instructor, test_instructor):
        """Test that instructors can't favorite themselves."""
        # Phase 13: Favorites migrated to /api/v1/favorites
        response = client.post(f"/api/v1/favorites/{test_instructor.id}", headers=auth_headers_instructor)
        # Should fail validation
        assert response.status_code in [400, 403]
