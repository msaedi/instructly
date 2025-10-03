"""Repository-level dependency providers."""

from fastapi import Depends
from sqlalchemy.orm import Session

from ...repositories.background_job_repository import BackgroundJobRepository
from ...repositories.instructor_profile_repository import InstructorProfileRepository
from .database import get_db


def get_instructor_repo(db: Session = Depends(get_db)) -> InstructorProfileRepository:
    """Provide an InstructorProfileRepository instance."""

    return InstructorProfileRepository(db)


def get_background_job_repo(db: Session = Depends(get_db)) -> BackgroundJobRepository:
    """Provide a BackgroundJobRepository instance."""

    return BackgroundJobRepository(db)
