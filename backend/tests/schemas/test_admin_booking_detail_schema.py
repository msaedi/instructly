from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.admin_booking_detail import (
    AdminBookingNote,
    AdminNoteAuthor,
    BookingDetailMeta,
    BookingDetailResponse,
    BookingInfo,
    ParticipantInfo,
    RecommendedAction,
    ServiceInfo,
    TimelineEvent,
)


def test_admin_booking_detail_schema_models():
    now = datetime(2026, 2, 3, 12, 0, 0, tzinfo=timezone.utc)
    meta = BookingDetailMeta(generated_at=now, booking_id="bk1")
    service = ServiceInfo(slug="guitar", name="Guitar", category="music")
    participant = ParticipantInfo(id="u1", name="Student S.", email_hash="abc12345")
    booking = BookingInfo(
        id="bk1",
        status="CONFIRMED",
        scheduled_at=now,
        duration_minutes=60,
        location_type="online",
        service=service,
        student=participant,
        instructor=participant,
        created_at=now,
        updated_at=now,
    )
    note_author = AdminNoteAuthor(id="u1", email="admin@example.com")
    note = AdminBookingNote(
        id="n1",
        note="Internal note",
        visibility="internal",
        category="general",
        created_at=now,
        created_by=note_author,
    )
    response = BookingDetailResponse(
        meta=meta,
        booking=booking,
        timeline=[TimelineEvent(ts=now, event="BOOKING_CREATED")],
        payment=None,
        messages=None,
        webhooks=None,
        traces=None,
        admin_notes=[note],
        recommended_actions=[RecommendedAction(action="force_complete", reason="test", allowed=True)],
    )

    assert response.admin_notes[0].created_by.email == "admin@example.com"
