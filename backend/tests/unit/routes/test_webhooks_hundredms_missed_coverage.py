"""Coverage tests for webhooks_hundredms routes — missed branches and error paths."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import HTTPException
import pytest

from app.routes.v1 import webhooks_hundredms as wh


# ---------------------------------------------------------------------------
# L124: Naive datetime timezone normalization
# ---------------------------------------------------------------------------
def test_normalize_timestamp_naive():
    """Naive datetime should be replaced with UTC tzinfo."""
    naive = datetime(2025, 6, 1, 12, 0, 0)
    result = wh._HandledEventEnvelope._normalize_timestamp(naive)
    assert result.tzinfo is not None
    assert result.tzinfo == timezone.utc


def test_normalize_timestamp_aware():
    """Aware datetime should be converted to UTC."""
    import pytz

    eastern = pytz.timezone("US/Eastern")
    aware = eastern.localize(datetime(2025, 6, 1, 12, 0, 0))
    result = wh._HandledEventEnvelope._normalize_timestamp(aware)
    assert result.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# L243-248: Future-dated webhook rejection
# ---------------------------------------------------------------------------
def test_validate_replay_window_future_rejected():
    future = datetime.now(timezone.utc) + timedelta(minutes=10)
    with pytest.raises(HTTPException) as exc:
        wh._validate_replay_window(future)
    assert exc.value.status_code == 400
    assert "Invalid webhook timestamp" in exc.value.detail


def test_validate_replay_window_stale_rejected():
    stale = datetime.now(timezone.utc) - timedelta(hours=7)
    with pytest.raises(HTTPException) as exc:
        wh._validate_replay_window(stale)
    assert exc.value.status_code == 400
    assert "Stale webhook" in exc.value.detail


def test_validate_replay_window_valid():
    now = datetime.now(timezone.utc)
    wh._validate_replay_window(now)  # Should not raise


# ---------------------------------------------------------------------------
# L259: Unsupported event type → 400
# ---------------------------------------------------------------------------
def test_validate_handled_event_payload_unsupported_type():
    with pytest.raises(HTTPException) as exc:
        wh._validate_handled_event_payload({}, "some.unknown.event")
    assert exc.value.status_code == 400
    assert "Unsupported event type" in exc.value.detail


# ---------------------------------------------------------------------------
# L296: Negative Content-Length
# ---------------------------------------------------------------------------
def test_validate_webhook_body_size_negative():
    with pytest.raises(HTTPException) as exc:
        wh._validate_webhook_body_size(content_length_header="-1")
    assert exc.value.status_code == 400


def test_validate_webhook_body_size_too_large():
    with pytest.raises(HTTPException) as exc:
        wh._validate_webhook_body_size(content_length_header=str(2_000_000))
    assert exc.value.status_code == 413


def test_validate_webhook_body_size_invalid():
    with pytest.raises(HTTPException) as exc:
        wh._validate_webhook_body_size(content_length_header="not_a_number")
    assert exc.value.status_code == 400


def test_validate_webhook_body_size_empty_header():
    # Empty header string after strip → no validation error
    wh._validate_webhook_body_size(content_length_header="  ")


def test_validate_webhook_body_size_large_raw_body():
    large_body = b"x" * (wh._MAX_WEBHOOK_BODY_BYTES + 1)
    with pytest.raises(HTTPException) as exc:
        wh._validate_webhook_body_size(raw_body=large_body)
    assert exc.value.status_code == 413


# ---------------------------------------------------------------------------
# L365-366: Missing user_id in peer metadata
# ---------------------------------------------------------------------------
def test_extract_user_id_from_metadata_missing():
    assert wh._extract_user_id_from_metadata(None) is None
    assert wh._extract_user_id_from_metadata({}) is None
    assert wh._extract_user_id_from_metadata({"user_id": ""}) is None
    assert wh._extract_user_id_from_metadata({"user_id": 123}) is None


def test_extract_user_id_from_metadata_json_string():
    import json

    meta = json.dumps({"user_id": "user123"})
    assert wh._extract_user_id_from_metadata(meta) == "user123"


def test_extract_user_id_from_metadata_invalid_json():
    assert wh._extract_user_id_from_metadata("not-json") is None


def test_extract_user_id_from_metadata_dict():
    assert wh._extract_user_id_from_metadata({"user_id": "u1"}) == "u1"


# ---------------------------------------------------------------------------
# L435-439, L457-463: Attendance window validation
# ---------------------------------------------------------------------------
def _video_session():
    return SimpleNamespace(
        booking_id="bk-1",
        room_id="rm-1",
        instructor_peer_id=None,
        instructor_joined_at=None,
        instructor_left_at=None,
        student_peer_id=None,
        student_joined_at=None,
        student_left_at=None,
        provider_metadata=None,
    )


def _booking(instructor_id="instr-1", student_id="stud-1", start_utc=None, duration=60):
    return SimpleNamespace(
        id="bk-1",
        instructor_id=instructor_id,
        student_id=student_id,
        booking_start_utc=start_utc or (datetime.now(timezone.utc) + timedelta(minutes=5)),
        duration_minutes=duration,
    )


def test_handle_peer_join_invalid_attendance_window():
    """joined_at is None → attendance window validation fails → return False."""
    vs = _video_session()
    bk = _booking()
    data = {
        "role": "host",
        "peer_id": "p1",
        "user_id": "instr-1",
        "joined_at": None,
        "metadata": None,
    }
    result = wh._handle_peer_join(vs, bk, data)
    assert result is False


def test_handle_peer_join_missing_booking_start():
    """booking_start_utc is not datetime → skip."""
    vs = _video_session()
    bk = _booking()
    bk.booking_start_utc = None
    data = {
        "role": "host",
        "peer_id": "p1",
        "user_id": "instr-1",
        "joined_at": datetime.now(timezone.utc).isoformat(),
        "metadata": None,
    }
    result = wh._handle_peer_join(vs, bk, data)
    assert result is False


# ---------------------------------------------------------------------------
# L477-483, L490-496: Host/guest role mismatch
# ---------------------------------------------------------------------------
def test_handle_peer_join_host_role_mismatch():
    """User claims host but user_id doesn't match instructor_id."""
    now = datetime.now(timezone.utc)
    vs = _video_session()
    bk = _booking(start_utc=now + timedelta(minutes=5))
    data = {
        "role": "host",
        "peer_id": "p1",
        "user_id": "stud-1",  # student pretending to be host
        "joined_at": now.isoformat(),
        "metadata": None,
    }
    result = wh._handle_peer_join(vs, bk, data)
    assert result is False


def test_handle_peer_join_guest_role_mismatch():
    """User claims guest but user_id doesn't match student_id."""
    now = datetime.now(timezone.utc)
    vs = _video_session()
    bk = _booking(start_utc=now + timedelta(minutes=5))
    data = {
        "role": "guest",
        "peer_id": "p1",
        "user_id": "instr-1",  # instructor pretending to be guest
        "joined_at": now.isoformat(),
        "metadata": None,
    }
    result = wh._handle_peer_join(vs, bk, data)
    assert result is False


# ---------------------------------------------------------------------------
# L502-503: Unknown role
# ---------------------------------------------------------------------------
def test_handle_peer_join_unknown_role():
    now = datetime.now(timezone.utc)
    vs = _video_session()
    bk = _booking(start_utc=now + timedelta(minutes=5))
    data = {
        "role": "moderator",  # Unknown role
        "peer_id": "p1",
        "user_id": "instr-1",
        "joined_at": now.isoformat(),
        "metadata": None,
    }
    result = wh._handle_peer_join(vs, bk, data)
    assert result is False


# ---------------------------------------------------------------------------
# L456-463: Missing user_id after metadata fallback → skip
# ---------------------------------------------------------------------------
def test_handle_peer_join_missing_user_id_completely():
    """user_id is missing from both auth and metadata → skip."""
    now = datetime.now(timezone.utc)
    vs = _video_session()
    bk = _booking(start_utc=now + timedelta(minutes=5))
    data = {
        "role": "host",
        "peer_id": "p1",
        "user_id": None,
        "joined_at": now.isoformat(),
        "metadata": None,
    }
    result = wh._handle_peer_join(vs, bk, data)
    assert result is False


# ---------------------------------------------------------------------------
# Non-participant user_id → skip
# ---------------------------------------------------------------------------
def test_handle_peer_join_non_participant():
    now = datetime.now(timezone.utc)
    vs = _video_session()
    bk = _booking(start_utc=now + timedelta(minutes=5))
    data = {
        "role": "host",
        "peer_id": "p1",
        "user_id": "outsider-1",  # not instructor nor student
        "joined_at": now.isoformat(),
        "metadata": None,
    }
    result = wh._handle_peer_join(vs, bk, data)
    assert result is False


# ---------------------------------------------------------------------------
# L571-578: Student join backfill from leave event
# ---------------------------------------------------------------------------
def test_handle_peer_leave_student_backfill():
    """Student leave with no prior join → backfill from leave event."""
    now = datetime.now(timezone.utc)
    vs = _video_session()
    bk = _booking()
    data = {
        "role": "guest",
        "peer_id": "p1",
        "user_id": "stud-1",
        "joined_at": (now - timedelta(minutes=30)).isoformat(),
        "left_at": now.isoformat(),
    }
    wh._handle_peer_leave(vs, bk, data)
    assert vs.student_joined_at is not None
    assert vs.student_peer_id == "p1"


def test_handle_peer_leave_student_no_join_no_joined_at():
    """Student leave with no prior join and no joined_at → ignore."""
    vs = _video_session()
    bk = _booking()
    data = {
        "role": "guest",
        "peer_id": "p1",
        "user_id": "stud-1",
        "joined_at": None,
        "left_at": datetime.now(timezone.utc).isoformat(),
    }
    wh._handle_peer_leave(vs, bk, data)
    assert vs.student_joined_at is None


def test_handle_peer_leave_student_user_id_mismatch():
    """Student leave backfill but user_id mismatch → ignore."""
    vs = _video_session()
    bk = _booking()
    data = {
        "role": "guest",
        "peer_id": "p1",
        "user_id": "wrong-user",
        "joined_at": datetime.now(timezone.utc).isoformat(),
        "left_at": datetime.now(timezone.utc).isoformat(),
    }
    wh._handle_peer_leave(vs, bk, data)
    assert vs.student_joined_at is None


# ---------------------------------------------------------------------------
# Instructor leave backfill from leave event
# ---------------------------------------------------------------------------
def test_handle_peer_leave_instructor_backfill():
    now = datetime.now(timezone.utc)
    vs = _video_session()
    bk = _booking()
    data = {
        "role": "host",
        "peer_id": "p1",
        "user_id": "instr-1",
        "joined_at": (now - timedelta(minutes=30)).isoformat(),
        "left_at": now.isoformat(),
    }
    wh._handle_peer_leave(vs, bk, data)
    assert vs.instructor_joined_at is not None


def test_handle_peer_leave_instructor_user_id_mismatch():
    vs = _video_session()
    bk = _booking()
    data = {
        "role": "host",
        "peer_id": "p1",
        "user_id": "wrong-user",
        "joined_at": datetime.now(timezone.utc).isoformat(),
        "left_at": datetime.now(timezone.utc).isoformat(),
    }
    wh._handle_peer_leave(vs, bk, data)
    assert vs.instructor_joined_at is None


def test_handle_peer_leave_instructor_no_join_no_joined_at():
    vs = _video_session()
    bk = _booking()
    data = {
        "role": "host",
        "peer_id": "p1",
        "user_id": "instr-1",
        "joined_at": None,
        "left_at": datetime.now(timezone.utc).isoformat(),
    }
    wh._handle_peer_leave(vs, bk, data)
    assert vs.instructor_joined_at is None


# ---------------------------------------------------------------------------
# Successful host/guest join
# ---------------------------------------------------------------------------
def test_handle_peer_join_host_success():
    now = datetime.now(timezone.utc)
    vs = _video_session()
    bk = _booking(start_utc=now + timedelta(minutes=5))
    data = {
        "role": "host",
        "peer_id": "p1",
        "user_id": "instr-1",
        "joined_at": now.isoformat(),
        "metadata": None,
    }
    result = wh._handle_peer_join(vs, bk, data)
    assert result is True
    assert vs.instructor_peer_id == "p1"
    assert vs.instructor_joined_at is not None


def test_handle_peer_join_guest_success():
    now = datetime.now(timezone.utc)
    vs = _video_session()
    bk = _booking(start_utc=now + timedelta(minutes=5))
    data = {
        "role": "guest",
        "peer_id": "p2",
        "user_id": "stud-1",
        "joined_at": now.isoformat(),
        "metadata": None,
    }
    result = wh._handle_peer_join(vs, bk, data)
    assert result is True
    assert vs.student_peer_id == "p2"


# ---------------------------------------------------------------------------
# Outside join window
# ---------------------------------------------------------------------------
def test_handle_peer_join_outside_window():
    now = datetime.now(timezone.utc)
    vs = _video_session()
    # booking_start_utc is far in the future
    bk = _booking(start_utc=now + timedelta(hours=24))
    data = {
        "role": "host",
        "peer_id": "p1",
        "user_id": "instr-1",
        "joined_at": now.isoformat(),
        "metadata": None,
    }
    result = wh._handle_peer_join(vs, bk, data)
    assert result is False


# ---------------------------------------------------------------------------
# L751-755: Duplicate processing race (delivery cache)
# ---------------------------------------------------------------------------
def test_delivery_seen_and_mark():
    """Test delivery dedup cache."""
    wh._delivery_cache.clear()
    assert wh._delivery_seen("key-1") is False
    wh._mark_delivery("key-1")
    assert wh._delivery_seen("key-1") is True
    wh._unmark_delivery("key-1")
    assert wh._delivery_seen("key-1") is False


def test_delivery_seen_none_key():
    assert wh._delivery_seen(None) is False
    wh._mark_delivery(None)  # should not raise
    wh._unmark_delivery(None)  # should not raise


# ---------------------------------------------------------------------------
# Build delivery key
# ---------------------------------------------------------------------------
def test_build_delivery_key_with_event_id():
    key = wh._build_delivery_key("evt-123", "peer.join.success", {})
    assert key == "evt-123"


def test_build_delivery_key_without_event_id():
    data = {"room_id": "rm-1", "session_id": "ses-1", "peer_id": "p-1"}
    key = wh._build_delivery_key(None, "peer.join.success", data)
    assert key is not None
    assert "peer.join.success" in key
    assert "rm-1" in key


def test_build_delivery_key_with_peer_object():
    data = {"room_id": "rm-1", "session_id": "ses-1", "peer": {"id": "peer-obj-1"}}
    key = wh._build_delivery_key(None, "peer.join.success", data)
    assert "peer-obj-1" in key


def test_build_delivery_key_no_peer():
    data = {"room_id": "rm-1", "session_id": "ses-1"}
    key = wh._build_delivery_key(None, "session.open.success", data)
    assert "no-peer" in key


# ---------------------------------------------------------------------------
# Extract booking_id from room name
# ---------------------------------------------------------------------------
def test_extract_booking_id_valid():
    # 26-char ULID: all valid chars
    bid = wh._extract_booking_id_from_room_name("lesson-01HF4G12ABCDEF3456789XYZAB")
    assert bid == "01HF4G12ABCDEF3456789XYZAB"


def test_extract_booking_id_invalid():
    assert wh._extract_booking_id_from_room_name("room-abc") is None
    assert wh._extract_booking_id_from_room_name(None) is None
    assert wh._extract_booking_id_from_room_name("") is None


# ---------------------------------------------------------------------------
# Parse timestamp
# ---------------------------------------------------------------------------
def test_parse_timestamp_valid():
    ts = wh._parse_timestamp("2025-06-01T12:00:00Z")
    assert ts is not None
    assert ts.tzinfo is not None


def test_parse_timestamp_naive():
    ts = wh._parse_timestamp("2025-06-01T12:00:00")
    assert ts is not None
    assert ts.tzinfo == timezone.utc


def test_parse_timestamp_invalid():
    assert wh._parse_timestamp("not-a-date") is None
    assert wh._parse_timestamp(123) is None
    assert wh._parse_timestamp("") is None
    assert wh._parse_timestamp("  ") is None


# ---------------------------------------------------------------------------
# Append metadata
# ---------------------------------------------------------------------------
def test_append_metadata():
    vs = _video_session()
    vs.provider_metadata = None
    wh._append_metadata(vs, "session.open.success", {"room_id": "rm-1"})
    assert vs.provider_metadata is not None
    assert len(vs.provider_metadata["events"]) == 1

    wh._append_metadata(vs, "session.close.success", {"room_id": "rm-1"})
    assert len(vs.provider_metadata["events"]) == 2


# ---------------------------------------------------------------------------
# Process event — session open/close
# ---------------------------------------------------------------------------
def test_process_event_session_open():
    vs = _video_session()
    vs.session_id = None
    vs.session_started_at = None

    class FakeBookingRepo:
        def get_video_session_by_booking_id(self, _bid):
            return vs

        def get_by_id(self, _bid):
            return _booking()

        def flush(self):
            pass

    err, outcome = wh._process_hundredms_event(
        event_type="session.open.success",
        data={
            "room_name": "lesson-01HF4G12ABCDEF3456789XYZAB",
            "room_id": "rm-1",
            "session_id": "ses-123",
            "session_started_at": "2025-06-01T12:00:00Z",
        },
        booking_repo=FakeBookingRepo(),
    )
    assert outcome == "processed"
    assert vs.session_id == "ses-123"


def test_process_event_session_close():
    vs = _video_session()
    vs.session_started_at = None

    class FakeBookingRepo:
        def get_video_session_by_booking_id(self, _bid):
            return vs

        def get_by_id(self, _bid):
            return _booking()

        def flush(self):
            pass

    err, outcome = wh._process_hundredms_event(
        event_type="session.close.success",
        data={
            "room_name": "lesson-01HF4G12ABCDEF3456789XYZAB",
            "room_id": "rm-1",
            "session_id": "ses-123",
            "session_started_at": "2025-06-01T12:00:00Z",
            "session_stopped_at": "2025-06-01T13:00:00Z",
            "session_duration": 3600,
        },
        booking_repo=FakeBookingRepo(),
    )
    assert outcome == "processed"


def test_process_event_no_video_session():
    class FakeBookingRepo:
        def get_video_session_by_booking_id(self, _bid):
            return None

        def get_by_id(self, _bid):
            return None

        def flush(self):
            pass

    err, outcome = wh._process_hundredms_event(
        event_type="session.open.success",
        data={
            "room_name": "lesson-01HF4G12ABCDEF3456789XYZAB",
            "room_id": "rm-1",
        },
        booking_repo=FakeBookingRepo(),
    )
    assert outcome == "skipped"


def test_process_event_unrecognized_room():
    class FakeBookingRepo:
        def get_video_session_by_booking_id(self, _bid):
            return None

        def get_by_id(self, _bid):
            return None

        def flush(self):
            pass

    err, outcome = wh._process_hundredms_event(
        event_type="session.open.success",
        data={"room_name": "random-room", "room_id": "rm-1"},
        booking_repo=FakeBookingRepo(),
    )
    assert outcome == "skipped"


def test_process_event_no_booking():
    vs = _video_session()

    class FakeBookingRepo:
        def get_video_session_by_booking_id(self, _bid):
            return vs

        def get_by_id(self, _bid):
            return None

        def flush(self):
            pass

    err, outcome = wh._process_hundredms_event(
        event_type="session.open.success",
        data={
            "room_name": "lesson-01HF4G12ABCDEF3456789XYZAB",
            "room_id": "rm-1",
        },
        booking_repo=FakeBookingRepo(),
    )
    assert outcome == "skipped"
