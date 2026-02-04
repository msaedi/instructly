from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.repositories.booking_note_repository import BookingNoteRepository


def test_booking_note_repository_create_and_list_ordering(db, test_booking, test_student):
    repo = BookingNoteRepository(db)

    older = repo.create_note(
        booking_id=test_booking.id,
        created_by_id=test_student.id,
        note="First note",
        visibility="internal",
        category="general",
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    newer = repo.create_note(
        booking_id=test_booking.id,
        created_by_id=None,
        note="Second note",
        visibility="internal",
        category="general",
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.commit()

    notes = repo.list_for_booking(test_booking.id)
    assert [note.id for note in notes] == [newer.id, older.id]
    assert notes[0].created_by is None
    assert notes[1].created_by is not None
    assert notes[1].created_by.email == test_student.email

    assert "BookingNote" in repr(notes[0])


def test_booking_note_repository_handles_bad_input(db, monkeypatch):
    repo = BookingNoteRepository(db)
    try:
        repo.create_note(booking_id=None)
    except Exception as exc:
        assert "booking note" in str(exc).lower()

    def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(repo.db, "query", _boom)
    try:
        repo.list_for_booking("01INVALIDBOOKING000000000000")
    except Exception as exc:
        assert "booking notes" in str(exc).lower()
