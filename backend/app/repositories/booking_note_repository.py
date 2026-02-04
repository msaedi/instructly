# backend/app/repositories/booking_note_repository.py
"""Repository for booking admin notes."""

from __future__ import annotations

import logging
from typing import Any, List

from sqlalchemy.orm import Session, joinedload

from ..core.exceptions import RepositoryException
from ..models.booking_note import BookingNote
from .base_repository import BaseRepository


class BookingNoteRepository(BaseRepository[BookingNote]):
    """Data access for booking notes."""

    def __init__(self, db: Session):
        super().__init__(db, BookingNote)
        self.logger = logging.getLogger(__name__)

    def create_note(self, **kwargs: Any) -> BookingNote:
        try:
            note = BookingNote(**kwargs)
            self.db.add(note)
            self.db.flush()
            return note
        except Exception as exc:
            self.logger.error("Error creating booking note: %s", exc)
            raise RepositoryException(f"Failed to create booking note: {exc}")

    def list_for_booking(self, booking_id: str) -> List[BookingNote]:
        try:
            return (
                self.db.query(BookingNote)
                .options(joinedload(BookingNote.created_by))
                .filter(BookingNote.booking_id == booking_id)
                .order_by(BookingNote.created_at.desc())
                .all()
            )
        except Exception as exc:
            self.logger.error("Error listing booking notes: %s", exc)
            raise RepositoryException(f"Failed to list booking notes: {exc}")
