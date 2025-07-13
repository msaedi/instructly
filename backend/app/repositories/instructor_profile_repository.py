# backend/app/repositories/instructor_profile_repository.py
"""
Instructor Profile Repository for InstaInstru Platform

Handles all data access operations for instructor profiles with
optimized queries for relationships (user and services).

This repository eliminates N+1 query problems by using eager loading
for commonly accessed relationships.
"""

import logging
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..core.exceptions import RepositoryException
from ..models.instructor import InstructorProfile
from ..models.service import Service
from ..models.user import User
from .base_repository import BaseRepository

logger = logging.getLogger(__name__)


class InstructorProfileRepository(BaseRepository[InstructorProfile]):
    """
    Repository for instructor profile data access.

    Provides optimized queries with eager loading for user and services
    relationships to prevent N+1 query problems.
    """

    def __init__(self, db: Session):
        """Initialize with InstructorProfile model."""
        super().__init__(db, InstructorProfile)
        self.logger = logging.getLogger(__name__)

    def get_all_with_details(
        self, skip: int = 0, limit: int = 100, include_inactive_services: bool = False
    ) -> List[InstructorProfile]:
        """
        Get all instructor profiles with user and services eager loaded.

        This method solves the N+1 query problem by loading all related
        data in a single query with joins.

        Note: This method returns ALL services regardless of the include_inactive_services
        parameter. The service layer should handle filtering when converting to DTOs.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_inactive_services: DEPRECATED - kept for compatibility but ignored

        Returns:
            List of InstructorProfile objects with all relationships loaded
        """
        try:
            query = (
                self.db.query(InstructorProfile)
                .options(joinedload(InstructorProfile.user), joinedload(InstructorProfile.services))
                .offset(skip)
                .limit(limit)
            )

            profiles = query.all()

            # Return profiles with all services loaded
            # Let the service layer handle filtering
            return profiles

        except Exception as e:
            self.logger.error(f"Error getting all profiles with details: {str(e)}")
            raise RepositoryException(f"Failed to get instructor profiles: {str(e)}")

    def get_by_user_id_with_details(
        self, user_id: int, include_inactive_services: bool = False
    ) -> Optional[InstructorProfile]:
        """
        Get a single instructor profile by user_id with all relationships loaded.

        Note: This method returns ALL services regardless of the include_inactive_services
        parameter. The service layer should handle filtering when converting to DTOs.

        Args:
            user_id: The user ID
            include_inactive_services: DEPRECATED - kept for compatibility but ignored

        Returns:
            InstructorProfile with all relationships loaded, or None if not found
        """
        try:
            profile = (
                self.db.query(InstructorProfile)
                .options(joinedload(InstructorProfile.user), joinedload(InstructorProfile.services))
                .filter(InstructorProfile.user_id == user_id)
                .first()
            )

            # Return profile with all services loaded
            # Let the service layer handle filtering
            return profile

        except Exception as e:
            self.logger.error(f"Error getting profile by user_id: {str(e)}")
            raise RepositoryException(f"Failed to get instructor profile: {str(e)}")

    def get_profiles_by_area(self, area: str, skip: int = 0, limit: int = 100) -> List[InstructorProfile]:
        """
        Get instructor profiles that service a specific area.

        Args:
            area: The area to search for
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of profiles that service the area
        """
        try:
            return (
                self.db.query(InstructorProfile)
                .options(joinedload(InstructorProfile.user), joinedload(InstructorProfile.services))
                .filter(InstructorProfile.areas_of_service.ilike(f"%{area}%"))
                .offset(skip)
                .limit(limit)
                .all()
            )
        except Exception as e:
            self.logger.error(f"Error getting profiles by area: {str(e)}")
            raise RepositoryException(f"Failed to get profiles by area: {str(e)}")

    def get_profiles_by_experience(self, min_years: int, skip: int = 0, limit: int = 100) -> List[InstructorProfile]:
        """
        Get instructor profiles with minimum years of experience.

        Args:
            min_years: Minimum years of experience
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of profiles with sufficient experience
        """
        try:
            return (
                self.db.query(InstructorProfile)
                .options(joinedload(InstructorProfile.user), joinedload(InstructorProfile.services))
                .filter(InstructorProfile.years_experience >= min_years)
                .offset(skip)
                .limit(limit)
                .all()
            )
        except Exception as e:
            self.logger.error(f"Error getting profiles by experience: {str(e)}")
            raise RepositoryException(f"Failed to get profiles by experience: {str(e)}")

    def count_profiles(self) -> int:
        """
        Count total number of instructor profiles.

        Returns:
            Number of profiles
        """
        try:
            return self.db.query(InstructorProfile).count()
        except Exception as e:
            self.logger.error(f"Error counting active profiles: {str(e)}")
            raise RepositoryException(f"Failed to count profiles: {str(e)}")

    def find_by_filters(
        self,
        search: Optional[str] = None,
        skill: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[InstructorProfile]:
        """
        Find instructor profiles based on multiple filter criteria.

        All filters are applied with AND logic - profiles must match ALL provided filters.

        Args:
            search: Text search across user.full_name, bio, and service skills (case-insensitive)
            skill: Filter by specific skill/service (case-insensitive)
            min_price: Minimum hourly rate filter
            max_price: Maximum hourly rate filter
            skip: Number of records to skip for pagination
            limit: Maximum number of records to return

        Returns:
            List of InstructorProfile objects matching all provided filters
        """
        import time

        start_time = time.time()

        try:
            # Start with base query including eager loading
            query = (
                self.db.query(InstructorProfile)
                .join(User, InstructorProfile.user_id == User.id)
                .join(Service, InstructorProfile.id == Service.instructor_profile_id)
                .options(joinedload(InstructorProfile.user), joinedload(InstructorProfile.services))
            )

            # Apply search filter if provided
            if search:
                search_term = f"%{search}%"
                query = query.filter(
                    or_(
                        User.full_name.ilike(search_term),
                        InstructorProfile.bio.ilike(search_term),
                        Service.skill.ilike(search_term),
                    )
                )

            # Apply skill filter if provided
            if skill:
                query = query.filter(Service.skill.ilike(f"%{skill}%"))

            # Apply price range filters if provided
            if min_price is not None:
                query = query.filter(Service.hourly_rate >= min_price)

            if max_price is not None:
                query = query.filter(Service.hourly_rate <= max_price)

            # Ensure we only get active services
            query = query.filter(Service.is_active == True)

            # Remove duplicates (since joins can create multiple rows per profile)
            # and apply pagination
            profiles = query.distinct().offset(skip).limit(limit).all()

            # Log query performance
            query_time = time.time() - start_time
            self.logger.info(
                f"Filter query completed in {query_time:.3f}s - "
                f"Filters: search={bool(search)}, skill={bool(skill)}, "
                f"price_range={bool(min_price or max_price)}, "
                f"Results: {len(profiles)} profiles"
            )

            # Log slow queries for optimization
            if query_time > 0.5:  # 500ms threshold
                self.logger.warning(
                    f"Slow filter query detected ({query_time:.3f}s) - "
                    f"Consider adding indexes for: "
                    f"{'search' if search else ''} "
                    f"{'skill' if skill else ''} "
                    f"{'price' if min_price or max_price else ''}"
                )

            return profiles

        except Exception as e:
            self.logger.error(f"Error finding profiles by filters: {str(e)}")
            raise RepositoryException(f"Failed to find profiles by filters: {str(e)}")

    # Override the base eager loading method
    def _apply_eager_loading(self, query):
        """
        Apply eager loading for commonly accessed relationships.

        This is called by BaseRepository methods like get_by_id()
        when load_relationships=True.
        """
        return query.options(joinedload(InstructorProfile.user), joinedload(InstructorProfile.services))
