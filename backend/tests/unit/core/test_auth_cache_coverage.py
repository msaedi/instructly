import asyncio
from datetime import datetime, timezone
import json

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
    payload = {"id": "01ARZ3NDEKTSV4RRFFQ69G5FAV", "email": "hit@example.com"}
    redis = StubRedis(hit_payload=json.dumps(payload))

    async def fake_get_client():
        return redis

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client)

    hit = await auth_cache.get_cached_user("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert hit == payload

    redis.hit_payload = None
    miss = await auth_cache.get_cached_user("01ARZ3NDEKTSV4RRFFQ69G5FB0")
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

    assert await auth_cache.get_cached_user("01ARZ3NDEKTSV4RRFFQ69G5FAV") is None


@pytest.mark.asyncio
async def test_get_cached_user_exception(monkeypatch):
    redis = StubRedis(raise_get=True)

    async def fake_get_client():
        return redis

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client)

    assert await auth_cache.get_cached_user("01ARZ3NDEKTSV4RRFFQ69G5FAV") is None


@pytest.mark.asyncio
async def test_set_cached_user_success_and_error(monkeypatch):
    redis = StubRedis()

    async def fake_get_client():
        return redis

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client)

    await auth_cache.set_cached_user("01ARZ3NDEKTSV4RRFFQ69G5FAV", {"id": "1"})
    assert redis.set_calls

    redis.raise_set = True
    await auth_cache.set_cached_user("01ARZ3NDEKTSV4RRFFQ69G5FAV", {"id": "1"})


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
    assert cache_keys == ["auth_user:id:01ARZ3NDEKTSV4RRFFQ69G5FAV"]


@pytest.mark.asyncio
async def test_set_cached_user_no_redis(monkeypatch):
    async def fake_get_client():
        return None

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client)

    await auth_cache.set_cached_user("01ARZ3NDEKTSV4RRFFQ69G5FAV", {"id": "1"})


@pytest.mark.asyncio
async def test_invalidate_cached_user_paths(monkeypatch):
    async def fake_get_client_none():
        return None

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client_none)
    assert await auth_cache.invalidate_cached_user("01ARZ3NDEKTSV4RRFFQ69G5FAV") is False

    redis = StubRedis(delete_value=1)

    async def fake_get_client():
        return redis

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client)
    assert await auth_cache.invalidate_cached_user("01ARZ3NDEKTSV4RRFFQ69G5FAV") is True

    redis.raise_get = True
    assert await auth_cache.invalidate_cached_user("01ARZ3NDEKTSV4RRFFQ69G5FAV") is False

    redis.delete_value = 0
    redis.raise_get = False
    assert await auth_cache.invalidate_cached_user("01ARZ3NDEKTSV4RRFFQ69G5FAV") is False


def test_invalidate_cached_user_by_id_sync_empty_id_returns_false():
    assert auth_cache.invalidate_cached_user_by_id_sync("", object()) is False


def test_invalidate_cached_user_by_id_sync_event_loop_running(monkeypatch):
    class StubLoop:
        def __init__(self):
            self.tasks = []

        def create_task(self, coro):
            coro.close()
            self.tasks.append("closed")

    async def fake_invalidate(_email):
        return True

    loop = StubLoop()
    monkeypatch.setattr(auth_cache, "invalidate_cached_user", fake_invalidate)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)

    assert auth_cache.invalidate_cached_user_by_id_sync("user-id", object()) is True
    assert loop.tasks


def test_invalidate_cached_user_by_id_sync_no_event_loop(monkeypatch):
    async def fake_invalidate(_email):
        return True

    monkeypatch.setattr(auth_cache, "invalidate_cached_user", fake_invalidate)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: (_ for _ in ()).throw(RuntimeError()))

    def fake_run(coro):
        coro.close()
        return True

    monkeypatch.setattr(asyncio, "run", fake_run)

    assert auth_cache.invalidate_cached_user_by_id_sync("user-id", object()) is True


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
    async def fake_get_cached(_user_id):
        return {"id": "cached"}

    async def fake_set_cached(_user_id, _data):
        raise AssertionError("set_cached_user should not be called")

    monkeypatch.setattr(auth_cache, "get_cached_user", fake_get_cached)
    monkeypatch.setattr(auth_cache, "set_cached_user", fake_set_cached)

    cached = await auth_cache.lookup_user_nonblocking("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert cached == {"id": "cached"}

    async def fake_get_cached_miss(_user_id):
        return None

    async def fake_set_cached_ok(_user_id, _data):
        return None

    async def fake_to_thread(func, *args, **kwargs):
        return {"id": "db"}

    monkeypatch.setattr(auth_cache, "get_cached_user", fake_get_cached_miss)
    monkeypatch.setattr(auth_cache, "set_cached_user", fake_set_cached_ok)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    result = await auth_cache.lookup_user_nonblocking("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert result == {"id": "db"}


@pytest.mark.asyncio
async def test_lookup_user_nonblocking_no_user(monkeypatch):
    async def fake_get_cached(_user_id):
        return None

    async def fake_set_cached(_user_id, _data):
        raise AssertionError("set_cached_user should not be called")

    async def fake_to_thread(func, *args, **kwargs):
        return None

    monkeypatch.setattr(auth_cache, "get_cached_user", fake_get_cached)
    monkeypatch.setattr(auth_cache, "set_cached_user", fake_set_cached)
    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)

    assert await auth_cache.lookup_user_nonblocking("01ARZ3NDEKTSV4RRFFQ69G5FAV") is None


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
async def test_lookup_user_nonblocking_is_ulid_alias(monkeypatch):
    expected = {"id": "01ARZ3NDEKTSV4RRFFQ69G5FAV"}

    async def fake_lookup(_user_id):
        return expected

    monkeypatch.setattr(auth_cache, "lookup_user_by_id_nonblocking", fake_lookup)

    result = await auth_cache.lookup_user_nonblocking("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert result == expected


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


# ── Coverage tests for empty-input guard branches ──


@pytest.mark.asyncio
async def test_get_cached_user_empty_user_id_returns_none():
    """get_cached_user returns None immediately when user_id is empty (line 63)."""
    result = await auth_cache.get_cached_user("")
    assert result is None

    result = await auth_cache.get_cached_user(None)
    assert result is None


@pytest.mark.asyncio
async def test_set_cached_user_empty_cache_user_id_returns_early(monkeypatch):
    """set_cached_user returns early when derived cache_user_id is empty (line 96-97)."""
    redis = StubRedis()

    async def fake_get_client():
        return redis

    monkeypatch.setattr(auth_cache, "_get_auth_redis_client", fake_get_client)

    # user_data has no 'id' key and user_id is empty string → cache_user_id = ""
    await auth_cache.set_cached_user("", {"email": "test@example.com"})
    # Should not have set anything
    assert redis.set_calls == []

    # user_data has empty 'id' key
    await auth_cache.set_cached_user("", {"id": "", "email": "test@example.com"})
    assert redis.set_calls == []

    # user_data has whitespace-only 'id'
    await auth_cache.set_cached_user("", {"id": "   ", "email": "test@example.com"})
    assert redis.set_calls == []


@pytest.mark.asyncio
async def test_invalidate_cached_user_empty_user_id_returns_false():
    """invalidate_cached_user returns False when user_id is empty (line 120-121)."""
    result = await auth_cache.invalidate_cached_user("")
    assert result is False


# ── Coverage tests for _on_done callback in invalidate_cached_user_by_id_sync (lines 163-167) ──


def test_invalidate_sync_task_done_callback_with_exception(monkeypatch, caplog):
    """The _on_done callback logs when task has an exception (lines 163-167)."""
    import logging

    callback_ref = [None]

    class StubTask:
        def __init__(self):
            self._done_callbacks = []

        def add_done_callback(self, fn):
            self._done_callbacks.append(fn)
            callback_ref[0] = fn

        def cancelled(self):
            return False

        def exception(self):
            return RuntimeError("cache invalidation failed")

    class StubLoop:
        def __init__(self):
            self.tasks = []

        def create_task(self, coro):
            # Close the coroutine to prevent warnings
            coro.close()
            task = StubTask()
            self.tasks.append(task)
            return task

    async def fake_invalidate(_user_id):
        return True

    loop = StubLoop()
    monkeypatch.setattr(auth_cache, "invalidate_cached_user", fake_invalidate)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)

    result = auth_cache.invalidate_cached_user_by_id_sync("user-id-123", object())
    assert result is True

    # Now trigger the done callback with the exception
    assert len(loop.tasks) == 1
    task = loop.tasks[0]
    assert len(task._done_callbacks) == 1

    with caplog.at_level(logging.ERROR):
        task._done_callbacks[0](task)

    assert any(
        "Fire-and-forget cache invalidation failed" in rec.message for rec in caplog.records
    )


def test_invalidate_sync_task_done_callback_cancelled(monkeypatch):
    """The _on_done callback returns early when task is cancelled (line 163-164)."""
    callback_ref = [None]

    class StubTask:
        def add_done_callback(self, fn):
            callback_ref[0] = fn

        def cancelled(self):
            return True

        def exception(self):
            raise AssertionError("should not be called if cancelled")

    class StubLoop:
        def create_task(self, coro):
            coro.close()
            return StubTask()

    async def fake_invalidate(_user_id):
        return True

    loop = StubLoop()
    monkeypatch.setattr(auth_cache, "invalidate_cached_user", fake_invalidate)
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: loop)

    auth_cache.invalidate_cached_user_by_id_sync("user-id", object())
    # Call the callback — should not raise since task is cancelled
    callback_ref[0](StubTask())


# ── Coverage tests for outer exception in invalidate_cached_user_by_id_sync (lines 180-182) ──


def test_invalidate_sync_outer_exception_returns_false(monkeypatch, caplog):
    """invalidate_cached_user_by_id_sync catches outer exceptions (lines 180-182)."""
    import logging

    # Make get_running_loop raise RuntimeError (no event loop)
    monkeypatch.setattr(
        asyncio, "get_running_loop", lambda: (_ for _ in ()).throw(RuntimeError("no loop"))
    )
    # Make asyncio.run raise an unexpected error
    monkeypatch.setattr(
        asyncio, "run", lambda coro: (_ for _ in ()).throw(Exception("unexpected outer failure"))
    )

    with caplog.at_level(logging.WARNING):
        result = auth_cache.invalidate_cached_user_by_id_sync("user-id", object())

    assert result is False
    assert any("Sync invalidation failed" in rec.message for rec in caplog.records)


# ── Coverage tests for user_has_cached_permission ORM fallback loop (lines 396-397) ──


def test_user_has_cached_permission_orm_fallback_iterates_roles():
    """user_has_cached_permission falls back to iterating role.permissions for ORM users (lines 395-398)."""
    user = User(email="orm@example.com")
    role1 = Role()
    perm_a = Permission()
    perm_a.name = "perm.a"
    perm_b = Permission()
    perm_b.name = "perm.b"
    role1.permissions = [perm_a, perm_b]

    role2 = Role()
    perm_c = Permission()
    perm_c.name = "perm.c"
    role2.permissions = [perm_c]

    user.roles = [role1, role2]

    # Ensure no cached permissions
    if hasattr(user, "_cached_permissions"):
        delattr(user, "_cached_permissions")

    # Should find perm.c in second role (full iteration of outer+inner loop)
    assert auth_cache.user_has_cached_permission(user, "perm.c") is True
    # Should not find a permission that doesn't exist
    assert auth_cache.user_has_cached_permission(user, "perm.d") is False
