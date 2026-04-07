"""Instructor profile repository facade backed by focused internal mixins."""

import logging

from sqlalchemy.orm import Session

from ..models.instructor import InstructorProfile
from .base_repository import BaseRepository
from .instructor_profile.bgc_lifecycle_mixin import BgcLifecycleMixin
from .instructor_profile.bgc_report_binding_mixin import BgcReportBindingMixin
from .instructor_profile.discovery_search_mixin import DiscoverySearchMixin
from .instructor_profile.eager_loading_mixin import EagerLoadingMixin
from .instructor_profile.founding_instructor_mixin import FoundingInstructorMixin
from .instructor_profile.profile_query_mixin import ProfileQueryMixin

logger = logging.getLogger(__name__)


class InstructorProfileRepository(
    ProfileQueryMixin,
    BgcLifecycleMixin,
    BgcReportBindingMixin,
    DiscoverySearchMixin,
    FoundingInstructorMixin,
    EagerLoadingMixin,
    BaseRepository[InstructorProfile],
):
    """Repository facade for instructor profile data access."""

    def __init__(self, db: Session) -> None:
        """Initialize with InstructorProfile model."""
        super().__init__(db, InstructorProfile)
        self.logger = logging.getLogger(__name__)
