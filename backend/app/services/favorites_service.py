"""
Favorites Service for InstaInstru Platform

Manages the business logic for user favorites functionality.
Handles validation, caching, and coordination between repositories.
"""

import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from ..core.enums import RoleName
from ..core.exceptions import NotFoundException, ValidationException
from ..models.user import User
from ..repositories.factory import RepositoryFactory
from ..repositories.favorites_repository import FavoritesRepository
from .base import BaseService
from .cache_service import CacheService

logger = logging.getLogger(__name__)


class FavoritesService(BaseService):
    """
    Service for managing user favorites.

    Provides business logic for students favoriting instructors,
    including validation, caching, and favorite management.
    """

    def __init__(
        self,
        db: Session,
        cache_service: Optional[CacheService] = None,
        favorites_repository: Optional[FavoritesRepository] = None,
        user_repository=None,
    ):
        """Initialize favorites service with dependencies."""
        super().__init__(db, cache=cache_service)
        self.logger = logging.getLogger(__name__)

        # Initialize repositories
        self.favorites_repository = favorites_repository or FavoritesRepository(db)
        self.user_repository = user_repository or RepositoryFactory.create_user_repository(db)

        # Cache configuration
        self.cache_ttl = 300  # 5 minutes

    @BaseService.measure_operation("add_favorite")
    def add_favorite(self, student_id: str, instructor_id: str) -> Dict[str, any]:
        """
        Add an instructor to a student's favorites.

        Args:
            student_id: ID of the student adding the favorite
            instructor_id: ID of the instructor to favorite

        Returns:
            Dictionary with success status and message

        Raises:
            ValidationException: If validation fails
            NotFoundException: If users not found
        """
        self.log_operation("add_favorite", student_id=student_id, instructor_id=instructor_id)

        # Validate student exists and is actually a student
        _student = self._validate_student(student_id)

        # Validate instructor exists and is actually an instructor
        _instructor = self._validate_instructor(instructor_id)

        # Prevent students from favoriting themselves (edge case)
        if student_id == instructor_id:
            raise ValidationException("Cannot favorite yourself")

        try:
            # Add the favorite
            favorite = self.favorites_repository.add_favorite(student_id, instructor_id)

            if favorite:
                # Invalidate cache
                self._invalidate_favorite_cache(student_id, instructor_id)

                return {
                    "success": True,
                    "message": "Instructor added to favorites",
                    "favorite_id": favorite.id,
                }
            else:
                # Already favorited
                return {
                    "success": False,
                    "message": "Instructor already in favorites",
                    "already_favorited": True,
                }

        except Exception as e:
            self.logger.error(f"Error adding favorite: {str(e)}")
            raise ValidationException(f"Failed to add favorite: {str(e)}")

    @BaseService.measure_operation("remove_favorite")
    def remove_favorite(self, student_id: str, instructor_id: str) -> Dict[str, any]:
        """
        Remove an instructor from a student's favorites.

        Args:
            student_id: ID of the student removing the favorite
            instructor_id: ID of the instructor to unfavorite

        Returns:
            Dictionary with success status and message

        Raises:
            ValidationException: If validation fails
            NotFoundException: If users not found
        """
        self.log_operation("remove_favorite", student_id=student_id, instructor_id=instructor_id)

        # Validate student exists and is actually a student
        _student = self._validate_student(student_id)

        # Validate instructor exists
        _instructor = self._validate_instructor(instructor_id)

        try:
            # Remove the favorite
            removed = self.favorites_repository.remove_favorite(student_id, instructor_id)

            if removed:
                # Invalidate cache
                self._invalidate_favorite_cache(student_id, instructor_id)

                return {"success": True, "message": "Instructor removed from favorites"}
            else:
                # Not favorited
                return {
                    "success": False,
                    "message": "Instructor not in favorites",
                    "not_favorited": True,
                }

        except Exception as e:
            self.logger.error(f"Error removing favorite: {str(e)}")
            raise ValidationException(f"Failed to remove favorite: {str(e)}")

    @BaseService.measure_operation("is_favorited")
    def is_favorited(self, student_id: str, instructor_id: str) -> bool:
        """
        Check if a student has favorited an instructor.
        Uses caching for performance.

        Args:
            student_id: ID of the student
            instructor_id: ID of the instructor

        Returns:
            True if favorited, False otherwise
        """
        # Check cache first
        cache_key = self._get_cache_key(student_id, instructor_id)

        if self.cache:
            cached_value = self.cache.get(cache_key)
            if cached_value is not None:
                return cached_value == "1"

        # Check database
        is_fav = self.favorites_repository.is_favorited(student_id, instructor_id)

        # Cache the result
        if self.cache:
            self.cache.set(cache_key, "1" if is_fav else "0", ttl=self.cache_ttl)

        return is_fav

    @BaseService.measure_operation("get_student_favorites")
    def get_student_favorites(self, student_id: str) -> List[User]:
        """
        Get all instructors favorited by a student.

        Args:
            student_id: ID of the student

        Returns:
            List of favorited instructors with profiles

        Raises:
            NotFoundException: If student not found
        """
        self.log_operation("get_student_favorites", student_id=student_id)

        # Validate student exists
        _student = self._validate_student(student_id)

        # Get favorites with instructor profiles
        favorites = self.favorites_repository.get_favorites_with_details(student_id)

        self.logger.info(f"Retrieved {len(favorites)} favorites for student {student_id}")
        return favorites

    @BaseService.measure_operation("get_instructor_stats")
    def get_instructor_favorite_stats(self, instructor_id: str) -> Dict[str, any]:
        """
        Get favorite statistics for an instructor.

        Args:
            instructor_id: ID of the instructor

        Returns:
            Dictionary with favorite count and other stats
        """
        # Get favorite count
        favorite_count = self.favorites_repository.get_instructor_favorited_count(instructor_id)

        return {
            "favorite_count": favorite_count,
            "is_popular": favorite_count >= 10,  # Consider popular if 10+ favorites
        }

    @BaseService.measure_operation("bulk_check_favorites")
    def bulk_check_favorites(self, student_id: str, instructor_ids: List[str]) -> Dict[str, bool]:
        """
        Check favorite status for multiple instructors at once.
        Useful for listing pages.

        Args:
            student_id: ID of the student
            instructor_ids: List of instructor IDs to check

        Returns:
            Dictionary mapping instructor_id to favorited status
        """
        if not student_id:
            # Return all False if no student (guest user)
            return {instructor_id: False for instructor_id in instructor_ids}

        return self.favorites_repository.bulk_check_favorites(student_id, instructor_ids)

    def _validate_student(self, student_id: str) -> User:
        """
        Validate that a user exists and is a student.

        Args:
            student_id: ID of the user to validate

        Returns:
            User object if valid

        Raises:
            NotFoundException: If user not found
            ValidationException: If user is not a student
        """
        user = self.user_repository.get_with_roles(student_id)

        if not user:
            raise NotFoundException(f"Student not found: {student_id}")

        # Check if user has student role
        has_student_role = any(role.name == RoleName.STUDENT for role in user.roles)
        if not has_student_role:
            raise ValidationException("User is not a student")

        return user

    def _validate_instructor(self, instructor_id: str) -> User:
        """
        Validate that a user exists and is an instructor.

        Args:
            instructor_id: ID of the user to validate

        Returns:
            User object if valid

        Raises:
            NotFoundException: If user not found
            ValidationException: If user is not an instructor
        """
        user = self.user_repository.get_instructor(instructor_id)

        if not user:
            # Try regular user lookup for better error message
            user = self.user_repository.get_by_id(instructor_id)
            if user:
                raise ValidationException("User is not an instructor")
            else:
                raise NotFoundException(f"Instructor not found: {instructor_id}")

        return user

    def _get_cache_key(self, student_id: str, instructor_id: str) -> str:
        """Generate cache key for favorite status."""
        return f"favorites:{student_id}:{instructor_id}"

    def _invalidate_favorite_cache(self, student_id: str, instructor_id: str):
        """Invalidate cache entries related to a favorite."""
        if self.cache:
            cache_key = self._get_cache_key(student_id, instructor_id)
            self.cache.delete(cache_key)

            # Also invalidate any list caches if needed
            list_cache_key = f"favorites:list:{student_id}"
            self.cache.delete(list_cache_key)
