"""Repository-level dependency providers."""

from fastapi import Depends
from sqlalchemy.orm import Session

from ...repositories.instructor_profile_repository import InstructorProfileRepository
from .database import get_db


def get_instructor_repo(db: Session = Depends(get_db)) -> InstructorProfileRepository:
    """Provide an InstructorProfileRepository instance."""

    return InstructorProfileRepository(db)
