"""Search history repository facade backed by focused internal mixins."""

from sqlalchemy.orm import Session

from ..models.search_history import SearchHistory
from .base_repository import BaseRepository
from .search_history.cleanup_mixin import CleanupMixin
from .search_history.core_history_mixin import CoreHistoryMixin
from .search_history.guest_conversion_mixin import GuestConversionMixin
from .search_history.lifecycle_mixin import LifecycleMixin
from .search_history.privacy_mixin import PrivacyMixin


class SearchHistoryRepository(
    CoreHistoryMixin,
    LifecycleMixin,
    GuestConversionMixin,
    PrivacyMixin,
    CleanupMixin,
    BaseRepository[SearchHistory],
):
    """
    Repository for search history data access.

    Provides unified queries that work for both authenticated and guest users.
    """

    def __init__(self, db: Session) -> None:
        """Initialize with SearchHistory model."""
        super().__init__(db, SearchHistory)
