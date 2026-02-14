import asyncio
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from app.core import auth_cache
from app.models.rbac import Permission, Role
from app.models.user import User


class StubRedis:
    def __init__(self, *, hit_payload=None, raise_get=False, raise_set=False, delete_value=1):
        self.hit_payload = hit_payload
        self.raise_get = raise_get
        self.raise_set = raise_set
        self.delete_value = delete_value
        self.set_calls = []
        self.get_calls = []
        self.delete_calls = []

    async def get(self, key):
        self.get_calls.append(key)
        if self.raise_get:
            raise RuntimeError("get failed")
        return self.hit_payload

    async def setex(self, key, ttl, payload):
        if self.raise_set:
            raise RuntimeError("set failed")
        self.set_calls.append((key, ttl, payload))

    async def delete(self, key):
        self.delete_calls.append(key)
        if self.raise_get:
            raise RuntimeError("delete failed")
        return self.delete_value


@pytest.mark.asyncio
async def test_get_cached_user_hit_and_miss(monkeypatch):
    payload = {"id": "user1", "email": "hit@example.com"}
    redis = StubRedis(hit_payload=json.dumps(payload))

    async def fake_get_client():
        return redis

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client)

    hit = await auth_cache.get_cached_user("hit@example.com")
    assert hit == payload

    redis.hit_payload = None
    miss = await auth_cache.get_cached_user("miss@example.com")
    assert miss is None


@pytest.mark.asyncio
async def test_get_auth_redis_client_success(monkeypatch):
    async def fake_client():
        return "redis-client"

    monkeypatch.setattr(auth_cache, "get_async_cache_redis_client", fake_client)
    assert await auth_cache._get_auth_redis_client() == "redis-client"


@pytest.mark.asyncio
async def test_get_cached_user_redis_none(monkeypatch):
    async def fake_get_client():
        return None

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client)

    assert await auth_cache.get_cached_user("user@example.com") is None


@pytest.mark.asyncio
async def test_get_cached_user_exception(monkeypatch):
    redis = StubRedis(raise_get=True)

    async def fake_get_client():
        return redis

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client)

    assert await auth_cache.get_cached_user("user@example.com") is None


@pytest.mark.asyncio
async def test_set_cached_user_success_and_error(monkeypatch):
    redis = StubRedis()

    async def fake_get_client():
        return redis

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client)

    await auth_cache.set_cached_user("user@example.com", {"id": "1"})
    assert redis.set_calls

    redis.raise_set = True
    await auth_cache.set_cached_user("user@example.com", {"id": "1"})


@pytest.mark.asyncio
async def test_set_cached_user_writes_id_primary_key(monkeypatch):
    redis = StubRedis()

    async def fake_get_client():
        return redis

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client)

    await auth_cache.set_cached_user(
        "ignored",
        {"id": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "email": "user@example.com"},
    )
    cache_keys = [entry[0] for entry in redis.set_calls]
    assert "auth_user:id:01ARZ3NDEKTSV4RRFFQ69G5FAV" in cache_keys
    assert "auth_user:email:user@example.com" in cache_keys


@pytest.mark.asyncio
async def test_set_cached_user_no_redis(monkeypatch):
    async def fake_get_client():
        return None

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client)

    await auth_cache.set_cached_user("user@example.com", {"id": "1"})


@pytest.mark.asyncio
async def test_invalidate_cached_user_paths(monkeypatch):
    async def fake_get_client_none():
        return None

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client_none)
    assert await auth_cache.invalidate_cached_user("user@example.com") is False

    redis = StubRedis(delete_value=1)

    async def fake_get_client():
        return redis

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client)
    assert await auth_cache.invalidate_cached_user("user@example.com") is True

    redis.raise_get = True
    assert await auth_cache.invalidate_cached_user("user@example.com") is False

    redis.delete_value = 0
    redis.raise_get = False
    assert await auth_cache.invalidate_cached_user("user@example.com") is False


def test_invalidate_cached_user_by_id_sync_user_not_found(monkeypatch):
    class StubUserRepo:
        def __init__(self, _db):
            pass

        def get_by_id(self, _user_id):
            return None

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", StubUserRepo)

    assert auth_cache.invalidate_cached_user_by_id_sync("user-id", object()) is False


def test_invalidate_cached_user_by_id_sync_exception(monkeypatch):
    class StubUserRepo:
        def __init__(self, _db):
            raise RuntimeError("db down")

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", StubUserRepo)
    assert auth_cache.invalidate_cached_user_by_id_sync("user-id", object()) is False


def test_invalidate_cached_user_by_id_sync_event_loop_running(monkeypatch):
    class StubUserRepo:
        def __init__(self, _db):
            pass

        def get_by_id(self, _user_id):
            return SimpleNamespace(id="user-id", email="user@example.com")

    class StubLoop:
        def __init__(self):
            self.tasks = []

        def create_task(self, coro):
            coro.close()
            self.tasks.append("closed")

    async def fake_invalidate(_email):
        return True

    loop = StubLoop()
    monkeypatch.setattr("app.repositories.user_repository.UserRepository", StubUserRepo)
    monkeypatch.setattr(auth_cache, "invalidate_cached_user", fake_invalidate)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)

    assert auth_cache.invalidate_cached_user_by_id_sync("user-id", object()) is True
    assert loop.tasks


def test_invalidate_cached_user_by_id_sync_no_event_loop(monkeypatch):
    class StubUserRepo:
        def __init__(self, _db):
            pass

        def get_by_id(self, _user_id):
            return SimpleNamespace(id="user-id", email="user@example.com")

    async def fake_invalidate(_email):
        return True

    monkeypatch.setattr("app.repositories.user_repository.UserRepository", StubUserRepo)
    monkeypatch.setattr(auth_cache, "invalidate_cached_user", fake_invalidate)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: (_ for _ in ()).throw(RuntimeError()))
    def fake_run(coro):
        coro.close()
        return True

    monkeypatch.setattr(asyncio, "run", fake_run)

    assert auth_cache.invalidate_cached_user_by_id_sync("user-id", object()) is True


def test_sync_user_lookup_returns_none(monkeypatch):
    class StubSession:
        def __init__(self):
            self.rolled_back = False
            self.closed = False

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    class StubUserRepo:
        def __init__(self, _db):
            pass

        def get_by_email_with_roles_and_permissions(self, _email):
            return None

    monkeypatch.setattr(auth_cache, "SessionLocal", lambda: StubSession())
    monkeypatch.setattr("app.repositories.user_repository.UserRepository", StubUserRepo)

    assert auth_cache._sync_user_lookup("user@example.com") is None


def test_sync_user_lookup_returns_user(monkeypatch):
    class StubSession:
        def rollback(self):
            pass

        def close(self):
            pass

    user = User(email="user@example.com")
    role = Role()
    perm = Permission()
    perm.name = "perm.read"
    role.name = "member"
    role.permissions = [perm]
    user.roles = [role]
    user.id = "user1"
    user.is_active = True

    class StubUserRepo:
        def __init__(self, _db):
            pass

        def get_by_email_with_roles_and_permissions(self, _email):
            return user

    class StubBetaRepo:
        def __init__(self, _db):
            pass

        def get_latest_for_user(self, _user_id):
            return SimpleNamespace(role="beta", phase="phase1", invited_by_code="code")

    monkeypatch.setattr(auth_cache, "SessionLocal", lambda: StubSession())
    monkeypatch.setattr("app.repositories.user_repository.UserRepository", StubUserRepo)
    monkeypatch.setattr("app.repositories.beta_repository.BetaAccessRepository", StubBetaRepo)

    result = auth_cache._sync_user_lookup("user@example.com")
    assert result is not None
    assert result["permissions"] == ["perm.read"]


def test_sync_user_lookup_by_id_returns_none(monkeypatch):
    class StubSession:
        def rollback(self):
            pass

        def close(self):
            pass

    class StubUserRepo:
        def __init__(self, _db):
            pass

        def get_by_id_with_roles_and_permissions(self, _user_id):
            return None

    monkeypatch.setattr(auth_cache, "SessionLocal", lambda: StubSession())
    monkeypatch.setattr("app.repositories.user_repository.UserRepository", StubUserRepo)

    assert auth_cache._sync_user_lookup_by_id("user-id") is None


def test_sync_user_lookup_by_id_returns_user(monkeypatch):
    class StubSession:
        def rollback(self):
            pass

        def close(self):
            pass

    user = User(email="user@example.com")
    user.roles = []
    user.id = "user1"
    user.is_active = True

    class StubUserRepo:
        def __init__(self, _db):
            pass

        def get_by_id_with_roles_and_permissions(self, _user_id):
            return user

    class StubBetaRepo:
        def __init__(self, _db):
            pass

        def get_latest_for_user(self, _user_id):
            return None

    monkeypatch.setattr(auth_cache, "SessionLocal", lambda: StubSession())
    monkeypatch.setattr("app.repositories.user_repository.UserRepository", StubUserRepo)
    monkeypatch.setattr("app.repositories.beta_repository.BetaAccessRepository", StubBetaRepo)

    result = auth_cache._sync_user_lookup_by_id("user-id")
    assert result is not None
    assert result["email"] == "user@example.com"


def test_user_to_dict_includes_tokens_valid_after_ts():
    user = User(email="user@example.com")
    user.roles = []
    user.tokens_valid_after = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)

    result = auth_cache._user_to_dict(user)
    assert result["tokens_valid_after_ts"] == int(user.tokens_valid_after.timestamp())


@pytest.mark.asyncio
async def test_lookup_user_nonblocking_cache_hit_and_miss(monkeypatch):
    async def fake_get_cached(_email):
        return {"id": "cached"}

    async def fake_set_cached(_email, _data):
        raise AssertionError("set_cached_user should not be called")

    monkeypatch.setattr(auth_cache, "get_cached_user", fake_get_cached)
    monkeypatch.setattr(auth_cache, "set_cached_user", fake_set_cached)

    cached = await auth_cache.lookup_user_nonblocking("user@example.com")
    assert cached == {"id": "cached"}

    async def fake_get_cached_miss(_email):
        return None

    async def fake_set_cached_ok(_email, _data):
        return None

    async def fake_to_thread(func, *args, **kwargs):
        return {"id": "db"}

    monkeypatch.setattr(auth_cache, "get_cached_user", fake_get_cached_miss)
    monkeypatch.setattr(auth_cache, "set_cached_user", fake_set_cached_ok)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    result = await auth_cache.lookup_user_nonblocking("user@example.com")
    assert result == {"id": "db"}


@pytest.mark.asyncio
async def test_lookup_user_nonblocking_no_user(monkeypatch):
    async def fake_get_cached(_email):
        return None

    async def fake_set_cached(_email, _data):
        raise AssertionError("set_cached_user should not be called")

    async def fake_to_thread(func, *args, **kwargs):
        return None

    monkeypatch.setattr(auth_cache, "get_cached_user", fake_get_cached)
    monkeypatch.setattr(auth_cache, "set_cached_user", fake_set_cached)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    assert await auth_cache.lookup_user_nonblocking("user@example.com") is None


@pytest.mark.asyncio
async def test_lookup_user_by_id_nonblocking(monkeypatch):
    async def fake_get_cached(_identifier):
        return None

    async def fake_set_cached(_identifier, _data):
        return None

    async def fake_to_thread(func, *args, **kwargs):
        return {"id": "user1"}

    monkeypatch.setattr(auth_cache, "get_cached_user", fake_get_cached)
    monkeypatch.setattr(auth_cache, "set_cached_user", fake_set_cached)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    result = await auth_cache.lookup_user_by_id_nonblocking("user1")
    assert result == {"id": "user1"}


@pytest.mark.asyncio
async def test_lookup_user_nonblocking_prefers_id_then_fallback(monkeypatch):
    calls = []

    async def fake_get_cached(_identifier):
        return None

    async def fake_set_cached(_identifier, _data):
        return None

    async def fake_to_thread(func, *args, **kwargs):
        calls.append(func.__name__)
        if func.__name__ == "_sync_user_lookup_by_id":
            return None
        if func.__name__ == "_sync_user_lookup":
            return {"id": "db-user"}
        return None

    monkeypatch.setattr(auth_cache, "get_cached_user", fake_get_cached)
    monkeypatch.setattr(auth_cache, "set_cached_user", fake_set_cached)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    result = await auth_cache.lookup_user_nonblocking("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert result == {"id": "db-user"}
    assert calls == ["_sync_user_lookup_by_id", "_sync_user_lookup"]


def test_create_transient_user_and_permissions():
    user_data = {
        "id": "user1",
        "email": "user@example.com",
        "is_active": True,
        "is_instructor": True,
        "is_student": True,
        "is_admin": True,
        "permissions": ["perm.view"],
        "roles": ["INSTRUCTOR", "STUDENT", "ADMIN"],
        "beta_access": True,
    }
    user = auth_cache.create_transient_user(user_data)
    assert len(user.roles) == 3
    assert auth_cache.user_has_cached_permission(user, "perm.view") is True


def test_create_transient_user_without_roles():
    user = auth_cache.create_transient_user({"email": "no-roles@example.com"})
    assert user.roles == []


def test_user_has_cached_permission_fallback():
    user = User(email="user@example.com")
    role = Role()
    permission = Permission()
    permission.name = "perm.edit"
    role.permissions = [permission]
    user.roles = [role]

    if hasattr(user, "_cached_permissions"):
        delattr(user, "_cached_permissions")

    assert auth_cache.user_has_cached_permission(user, "perm.edit") is True


def test_user_has_cached_permission_false():
    user = User(email="user@example.com")
    user.roles = []
    if hasattr(user, "_cached_permissions"):
        delattr(user, "_cached_permissions")

    assert auth_cache.user_has_cached_permission(user, "perm.none") is False


def test_reset_redis_client_noop():
    auth_cache._reset_redis_client()
