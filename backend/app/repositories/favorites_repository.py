"""
Favorites Repository for InstaInstru Platform

Handles all database operations for user favorites functionality.
Provides methods for adding, removing, and querying favorite instructors.
"""

import logging
from typing import List, Optional, cast

from sqlalchemy import and_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from ..models.favorite import UserFavorite
from ..models.user import User
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class FavoritesRepository(BaseRepository[UserFavorite]):
    """
    Repository for managing user favorites.

    Provides database operations for students favoriting instructors,
    including adding/removing favorites and retrieving favorite lists.
    """

    def __init__(self, db: Session):
        """Initialize with UserFavorite model."""
        super().__init__(db, UserFavorite)
        self.logger = logging.getLogger(__name__)

    def add_favorite(self, student_id: str, instructor_id: str) -> Optional[UserFavorite]:
        """
        Add an instructor to a student's favorites.

        Args:
            student_id: ID of the student adding the favorite
            instructor_id: ID of the instructor being favorited

        Returns:
            UserFavorite object if successful, None if already exists

        Raises:
            IntegrityError: If the combination already exists (caught and returns None)
        """
        try:
            # Check if already favorited
            existing = self.is_favorited(student_id, instructor_id)
            if existing:
                self.logger.info(
                    f"Student {student_id} already favorited instructor {instructor_id}"
                )
                return None

            # Create new favorite
            favorite = UserFavorite(student_id=student_id, instructor_id=instructor_id)

            self.db.add(favorite)
            self.db.commit()
            self.db.refresh(favorite)

            self.logger.info(f"Student {student_id} favorited instructor {instructor_id}")
            return favorite

        except IntegrityError:
            self.db.rollback()
            self.logger.warning(
                f"Duplicate favorite attempted: student={student_id}, instructor={instructor_id}"
            )
            return None
        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error adding favorite: {str(e)}")
            raise

    def remove_favorite(self, student_id: str, instructor_id: str) -> bool:
        """
        Remove an instructor from a student's favorites.

        Args:
            student_id: ID of the student removing the favorite
            instructor_id: ID of the instructor being unfavorited

        Returns:
            True if removed, False if not found
        """
        try:
            favorite = (
                self.db.query(UserFavorite)
                .filter(
                    and_(
                        UserFavorite.student_id == student_id,
                        UserFavorite.instructor_id == instructor_id,
                    )
                )
                .first()
            )

            if not favorite:
                self.logger.info(
                    f"No favorite found for student {student_id} and instructor {instructor_id}"
                )
                return False

            self.db.delete(favorite)
            self.db.commit()

            self.logger.info(f"Student {student_id} unfavorited instructor {instructor_id}")
            return True

        except Exception as e:
            self.db.rollback()
            self.logger.error(f"Error removing favorite: {str(e)}")
            raise

    def is_favorited(self, student_id: str, instructor_id: str) -> bool:
        """
        Check if a student has favorited an instructor.

        Args:
            student_id: ID of the student
            instructor_id: ID of the instructor

        Returns:
            True if favorited, False otherwise
        """
        try:
            exists = (
                self.db.query(UserFavorite)
                .filter(
                    and_(
                        UserFavorite.student_id == student_id,
                        UserFavorite.instructor_id == instructor_id,
                    )
                )
                .first()
            )
            return exists is not None

        except Exception as e:
            self.logger.error(f"Error checking favorite status: {str(e)}")
            return False

    def get_student_favorites(self, student_id: str) -> List[User]:
        """
        Get all instructors favorited by a student.

        Args:
            student_id: ID of the student

        Returns:
            List of User objects (instructors) that the student has favorited
        """
        try:
            favorites = cast(
                List[User],
                self.db.query(User)
                .join(UserFavorite, UserFavorite.instructor_id == User.id)
                .filter(UserFavorite.student_id == student_id)
                .order_by(UserFavorite.created_at.desc())
                .all(),
            )

            self.logger.info(f"Retrieved {len(favorites)} favorites for student {student_id}")
            return favorites

        except Exception as e:
            self.logger.error(f"Error getting student favorites: {str(e)}")
            return []

    def get_favorites_with_details(self, student_id: str) -> List[User]:
        """
        Get favorited instructors with their profiles eagerly loaded.

        Args:
            student_id: ID of the student

        Returns:
            List of User objects with instructor_profile relationship loaded
        """
        try:
            favorites = cast(
                List[User],
                self.db.query(User)
                .join(UserFavorite, UserFavorite.instructor_id == User.id)
                .options(joinedload(User.instructor_profile), joinedload(User.roles))
                .filter(UserFavorite.student_id == student_id)
                .order_by(UserFavorite.created_at.desc())
                .all(),
            )

            self.logger.info(
                f"Retrieved {len(favorites)} favorites with details for student {student_id}"
            )
            return favorites

        except Exception as e:
            self.logger.error(f"Error getting favorites with details: {str(e)}")
            return []

    def get_instructor_favorited_count(self, instructor_id: str) -> int:
        """
        Get the number of students who have favorited an instructor.

        Args:
            instructor_id: ID of the instructor

        Returns:
            Count of students who favorited this instructor
        """
        try:
            count = (
                self.db.query(func.count(UserFavorite.id))
                .filter(UserFavorite.instructor_id == instructor_id)
                .scalar()
            )

            return count or 0

        except Exception as e:
            self.logger.error(
                f"Error getting favorite count for instructor {instructor_id}: {str(e)}"
            )
            return 0

    def get_favorite_ids_for_student(self, student_id: str) -> List[str]:
        """
        Get just the instructor IDs that a student has favorited.
        Useful for bulk checking favorite status.

        Args:
            student_id: ID of the student

        Returns:
            List of instructor IDs (strings)
        """
        try:
            instructor_ids = (
                self.db.query(UserFavorite.instructor_id)
                .filter(UserFavorite.student_id == student_id)
                .all()
            )

            return [id[0] for id in instructor_ids]

        except Exception as e:
            self.logger.error(f"Error getting favorite IDs: {str(e)}")
            return []

    def bulk_check_favorites(self, student_id: str, instructor_ids: List[str]) -> dict[str, bool]:
        """
        Check favorite status for multiple instructors at once.

        Args:
            student_id: ID of the student
            instructor_ids: List of instructor IDs to check

        Returns:
            Dictionary mapping instructor_id to favorited status
        """
        try:
            # Get all favorited instructor IDs for this student
            favorited_ids = set(self.get_favorite_ids_for_student(student_id))

            # Create result dictionary
            result = {
                instructor_id: instructor_id in favorited_ids for instructor_id in instructor_ids
            }

            return result

        except Exception as e:
            self.logger.error(f"Error bulk checking favorites: {str(e)}")
            # Return all False on error
            return {instructor_id: False for instructor_id in instructor_ids}
