from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
from types import SimpleNamespace

from app.models.booking import Booking
from app.models.user import User
from app.repositories import cached_repository_mixin as cached_module
from app.repositories.cached_repository_mixin import CachedRepositoryMixin, cached_method


class FakeCache:
    def __init__(self):
        self.store = {}
        self.deleted = []
        self.deleted_patterns = []

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ttl=None, tier=None):
        self.store[key] = value
        self.last_set = (key, ttl, tier)

    def delete(self, key):
        self.deleted.append(key)
        self.store.pop(key, None)

    def delete_pattern(self, pattern):
        self.deleted_patterns.append(pattern)
        return 1

    def get_stats(self):
        return {"keys": len(self.store)}


class DummyRepo(CachedRepositoryMixin):
    def __init__(self, cache):
        self.db = None
        self.init_cache(cache)

    @cached_method(ttl=10, tier="hot")
    def get_value(self, value, flag=True):
        return {"value": value, "flag": flag}


def test_cache_key_generation_and_serialization(db, test_instructor):
    repo = DummyRepo(FakeCache())

    key = repo._generate_cache_key("method", "abc", 1, date(2024, 1, 1), flag=True)
    assert "method" in key
    assert "abc" in key

    serialized = repo._serialize_for_cache(test_instructor)
    assert serialized["id"] == test_instructor.id
    assert serialized["_from_cache"] is True

    nested = repo._serialize_for_cache([{"k": "v"}])
    assert nested == [{"k": "v"}]


def test_cache_key_with_ids_and_hashes():
    repo = DummyRepo(FakeCache())
    obj_with_id = SimpleNamespace(id="obj-123")
    complex_obj = SimpleNamespace(value={"a": 1})

    key = repo._generate_cache_key("method", obj_with_id, complex_obj, flag=False)
    expected_hash = hashlib.md5(str(complex_obj).encode()).hexdigest()[:8]
    assert "id_obj-123" in key
    assert expected_hash in key


def test_serialize_for_cache_variants():
    repo = DummyRepo(FakeCache())

    assert repo._serialize_for_cache(None) is None
    assert repo._serialize_for_cache(datetime(2024, 1, 1, tzinfo=timezone.utc)) == "2024-01-01T00:00:00+00:00"
    assert repo._serialize_for_cache([1], _depth=2) == []

    class Blob:
        pass

    blob = Blob()
    assert repo._serialize_for_cache(blob) is blob


def test_serialize_for_cache_relationships_and_cycles():
    repo = DummyRepo(FakeCache())
    student = User(
        id="student-1",
        email="student@example.com",
        hashed_password="hash",
        first_name="Stu",
        last_name="Dent",
        phone="+12125550101",
        zip_code="10001",
    )
    instructor = User(
        id="instructor-1",
        email="instructor@example.com",
        hashed_password="hash",
        first_name="Ins",
        last_name="Tructor",
        phone="+12125550102",
        zip_code="10001",
    )
    service = SimpleNamespace(id="svc-1", name="Guitar", description="Basics")
    booking = Booking(id="booking-1", hourly_rate=10.0, total_price=10.0)
    booking.student = student
    booking.instructor = instructor
    booking.__dict__["instructor_service"] = service
    booking.rescheduled_from = booking

    serialized = repo._serialize_for_cache(booking)
    assert serialized["student"]["id"] == "student-1"
    assert serialized["instructor"]["email"] == "instructor@example.com"
    assert serialized["instructor_service"]["name"] == "Guitar"
    assert serialized["rescheduled_from"]["_circular_ref"] is True


def test_cache_service_fallback_and_invalidation(monkeypatch):
    repo = DummyRepo(None)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cached_module, "get_cache_service", _raise)
    assert repo.cache_service is None

    cache = FakeCache()
    repo.init_cache(cache)
    repo._invalidate_method_cache("method", "arg")
    assert cache.deleted

    repo.invalidate_entity_cache("123")
    repo.invalidate_all_cache()
    assert cache.deleted_patterns

    stats = repo.get_cache_stats()
    assert stats["repository"] == repo._cache_prefix


def test_cache_disabled_and_no_cache(monkeypatch):
    repo = DummyRepo(None)
    monkeypatch.setattr(cached_module, "get_cache_service", lambda *_args, **_kwargs: None)
    assert repo.cache_service is None

    repo._invalidate_method_cache("method", "arg")
    repo.invalidate_entity_cache("123")
    repo.invalidate_all_cache()
    assert repo.get_cache_stats() is None


def test_cached_method_hits_and_miss():
    cache = FakeCache()
    repo = DummyRepo(cache)

    result = repo.get_value("a", flag=False)
    assert result == {"value": "a", "flag": False}
    assert cache.store

    cache.store[next(iter(cache.store))] = {"cached": True}
    cached = repo.get_value("a", flag=False)
    assert cached == {"cached": True}


def test_cached_method_handles_cache_errors(monkeypatch):
    class ErrorCache(FakeCache):
        def get(self, key):
            raise RuntimeError("boom")

        def set(self, key, value, ttl=None, tier=None):
            raise RuntimeError("boom")

    repo = DummyRepo(ErrorCache())
    result = repo.get_value("err", flag=True)
    assert result == {"value": "err", "flag": True}

    monkeypatch.setattr(repo, "_serialize_for_cache", lambda *_args, **_kwargs: (_ for _ in ()).throw(RecursionError("loop")))
    result = repo.get_value("loop", flag=False)
    assert result == {"value": "loop", "flag": False}


def test_with_cache_disabled_context():
    cache = FakeCache()
    repo = DummyRepo(cache)

    with repo.with_cache_disabled():
        result = repo.get_value("b")
        assert not cache.store
    assert result == {"value": "b", "flag": True}


def test_invalidation_errors_are_handled():
    class FailingCache(FakeCache):
        def delete(self, key):
            raise RuntimeError("boom")

        def delete_pattern(self, pattern):
            raise RuntimeError("boom")

    repo = DummyRepo(FailingCache())
    repo._invalidate_method_cache("method", "arg")
    repo.invalidate_entity_cache("123")
    repo.invalidate_all_cache()
