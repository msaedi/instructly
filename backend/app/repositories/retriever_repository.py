"""Retriever repository facade backed by focused internal mixins."""

import logging

from sqlalchemy.orm import Session

from .retriever.candidate_search_mixin import CandidateSearchMixin
from .retriever.grouped_search_mixin import GroupedSearchMixin
from .retriever.instructor_hydration_mixin import InstructorHydrationMixin


class RetrieverRepository(
    CandidateSearchMixin,
    InstructorHydrationMixin,
    GroupedSearchMixin,
):
    """Repository facade for retriever queries."""

    def __init__(self, db: Session) -> None:
        """Initialize with database session."""
        self.db = db
        self.logger = logging.getLogger(__name__)
