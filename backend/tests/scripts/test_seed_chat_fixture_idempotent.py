import sys
import types

from scripts import seed_chat_fixture


def test_chat_fixture_idempotent(monkeypatch, capsys):
    monkeypatch.setenv("SEED_CHAT_FIXTURE", "1")

    # Stub booking module imported inside the fixture.
    class DummyBooking:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class _Status:
        def __init__(self, value):
            self.value = value

    booking_module = types.SimpleNamespace(
        Booking=DummyBooking,
        BookingStatus=types.SimpleNamespace(CONFIRMED=_Status("CONFIRMED"), PENDING=_Status("PENDING")),
    )
    monkeypatch.setitem(sys.modules, "app.models.booking", booking_module)

    profile = types.SimpleNamespace(id="profile-1", min_advance_booking_hours=1)
    service = types.SimpleNamespace(id="service-1", duration_options=[60], hourly_rate=80, name="Lesson")

    users = {
        "instructor@example.com": types.SimpleNamespace(id="inst-1", email="instructor@example.com"),
        "student@example.com": types.SimpleNamespace(id="stu-1", email="student@example.com"),
    }

    state = {"bookings": []}

    class FakeSession:
        def __init__(self):
            self.closed = False

        def add(self, booking):
            state["bookings"].append(booking)

        def commit(self):
            return None

        def rollback(self):
            state.setdefault("rollbacks", 0)
            state["rollbacks"] += 1

        def close(self):
            self.closed = True

    sessions = []

    def fake_session_factory():
        session = FakeSession()
        sessions.append(session)
        return session

    def fake_get_user(_session, email):
        return users.get(email)

    def fake_profile(session, instructor):
        return profile

    def fake_service(session, profile, duration_minutes, service_name):
        return service

    def fake_existing(session, instructor_id, student_id, now, horizon_days=14):
        for booking in state["bookings"]:
            if booking.instructor_id == instructor_id and booking.student_id == student_id:
                start_dt = seed_chat_fixture._localize(booking.booking_date, booking.start_time)
                if start_dt > now:
                    return booking
        return None

    def fake_conflict(session, instructor_id, target_day, start_time, end_time):
        for booking in state["bookings"]:
            if booking.booking_date != target_day:
                continue
            if booking.start_time < end_time and booking.end_time > start_time:
                return True
        return False

    def fake_candidate_times(day, base_hour, duration_minutes):
        naive_start = seed_chat_fixture.datetime.combine(day, seed_chat_fixture.time(hour=base_hour))
        naive_end = naive_start + seed_chat_fixture.timedelta(minutes=duration_minutes)
        return [(naive_start.time(), naive_end.time(), naive_start)]

    monkeypatch.setattr(seed_chat_fixture, "_get_user_by_email", fake_get_user)
    monkeypatch.setattr(seed_chat_fixture, "_ensure_profile", fake_profile)
    monkeypatch.setattr(seed_chat_fixture, "_ensure_service", fake_service)
    monkeypatch.setattr(seed_chat_fixture, "_ensure_bitmap_window", lambda *args, **kwargs: None)
    monkeypatch.setattr(seed_chat_fixture, "_existing_fixture", fake_existing)
    monkeypatch.setattr(seed_chat_fixture, "_has_booking_conflict", fake_conflict)
    monkeypatch.setattr(seed_chat_fixture, "_candidate_times", fake_candidate_times)

    result_first = seed_chat_fixture.seed_chat_fixture_booking(
        instructor_email="instructor@example.com",
        student_email="student@example.com",
        start_hour=17,
        duration_minutes=60,
        days_ahead_min=1,
        days_ahead_max=2,
        location="remote",
        service_name="Lesson",
        session_factory=fake_session_factory,
    )
    assert result_first == "created"
    assert len(state["bookings"]) == 1
    capsys.readouterr()

    result_second = seed_chat_fixture.seed_chat_fixture_booking(
        instructor_email="instructor@example.com",
        student_email="student@example.com",
        start_hour=17,
        duration_minutes=60,
        days_ahead_min=1,
        days_ahead_max=2,
        location="remote",
        service_name="Lesson",
        session_factory=fake_session_factory,
    )
    output = capsys.readouterr().out
    assert result_second == "skipped-existing"
    assert "chat fixture booking skipped: already exists" in output
    assert "transaction is already begun" not in output
    assert len(state["bookings"]) == 1
