from contextlib import contextmanager
import datetime as dt
from types import SimpleNamespace

from scripts.reset_and_seed_yaml import DatabaseSeeder


class DummySession:
    def __init__(self, scalar_values):
        self.scalar_values = list(scalar_values)
        self.calls = []
        self._index = 0

    @contextmanager
    def _no_autoflush_ctx(self):
        yield

    @property
    def no_autoflush(self):
        return self._no_autoflush_ctx()

    def execute(self, statement, params):
        self.calls.append(params)
        value = None
        if self._index < len(self.scalar_values):
            value = self.scalar_values[self._index]
            self._index += 1
        return SimpleNamespace(scalar=lambda: value)


def _new_seeder():
    return DatabaseSeeder.__new__(DatabaseSeeder)


def test_slot_conflicts_shortcircuits_pending():
    """Test that _slot_conflicts returns True when slot is in pending set."""
    seeder = _new_seeder()
    session = DummySession([])
    pending = {
        (
            "student-1",
            dt.date(2024, 11, 1),
            dt.time(10, 0),
            dt.time(11, 0),
        )
    }

    # check_instructor=False (default) checks student_id column
    assert seeder._slot_conflicts(
        session,
        "student-1",
        dt.date(2024, 11, 1),
        dt.time(10, 0),
        dt.time(11, 0),
        pending,
    )
    assert session.calls == []


def test_slot_conflicts_queries_session_when_needed():
    """Test that _slot_conflicts queries DB when slot not in pending set."""
    seeder = _new_seeder()
    date_value = dt.date(2024, 12, 5)
    start = dt.time(9, 0)
    end = dt.time(10, 0)
    session = DummySession([None, 1])
    pending = set()

    # check_instructor=False (default) checks student_id column
    assert (
        seeder._slot_conflicts(session, "student-2", date_value, start, end, pending)
        is False
    )
    assert session.calls[0] == {
        "user_id": "student-2",
        "booking_date": date_value,
        "start_time": start,
        "end_time": end,
    }

    assert (
        seeder._slot_conflicts(session, "student-2", date_value, start, end, pending)
        is True
    )
