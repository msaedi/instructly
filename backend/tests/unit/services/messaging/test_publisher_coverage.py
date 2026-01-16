from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.messaging import publisher


@pytest.mark.asyncio
async def test_publish_new_message_direct_sends_to_all(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    await publisher.publish_new_message_direct(
        participant_ids=["u1", "u2", "u1"],
        message_id="m1",
        content="hello",
        sender_id="u1",
        sender_name="Sender",
        conversation_id="c1",
        created_at=datetime.now(timezone.utc),
    )

    assert publish_mock.await_count == 2


@pytest.mark.asyncio
async def test_publish_typing_status_direct_excludes_typer(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    await publisher.publish_typing_status_direct(
        participant_ids=["u1", "u2"],
        conversation_id="c1",
        user_id="u1",
        user_name="User",
        is_typing=True,
    )

    publish_mock.assert_awaited_once()
    args, _ = publish_mock.await_args
    assert args[0] == "u2"


@pytest.mark.asyncio
async def test_publish_read_receipt_direct_no_participants(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    await publisher.publish_read_receipt_direct([], "c1", "u1", ["m1"])
    publish_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_new_message_skips_missing_conversation(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(publisher.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(publisher, "_get_conversation_participants_sync", lambda *_a, **_k: [])

    await publisher.publish_new_message(
        db=None,
        message_id="m1",
        content="hi",
        sender_id="u1",
        conversation_id="c1",
        created_at=datetime.now(timezone.utc),
    )
    publish_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_new_message_fetches_sender_name(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(publisher.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(
        publisher,
        "_get_conversation_participants_sync",
        lambda *_a, **_k: ["u1", "u2"],
    )
    monkeypatch.setattr(publisher, "_get_sender_name_sync", lambda *_a, **_k: "Name")

    await publisher.publish_new_message(
        db=None,
        message_id="m1",
        content="hi",
        sender_id="u1",
        conversation_id="c1",
        created_at=datetime.now(timezone.utc),
    )

    event = publish_mock.await_args.args[1]
    assert event["payload"]["message"]["sender_name"] == "Name"


def test_get_conversation_participants_sync_returns_ids(monkeypatch):
    class _Repo:
        def __init__(self, _db):
            pass

        def get_by_id(self, _conversation_id):
            return SimpleNamespace(student_id="student-1", instructor_id="inst-1")

    monkeypatch.setattr(publisher, "ConversationRepository", _Repo)
    assert publisher._get_conversation_participants_sync(None, "conv") == [
        "student-1",
        "inst-1",
    ]


def test_get_conversation_participants_sync_missing(monkeypatch):
    class _Repo:
        def __init__(self, _db):
            pass

        def get_by_id(self, _conversation_id):
            return None

    monkeypatch.setattr(publisher, "ConversationRepository", _Repo)
    assert publisher._get_conversation_participants_sync(None, "conv") == []


def test_get_sender_name_sync_builds_full_name(monkeypatch):
    class _UserRepo:
        def get_by_id(self, _sender_id):
            return SimpleNamespace(first_name="Ada", last_name="Lovelace")

    monkeypatch.setattr(
        publisher.RepositoryFactory, "create_user_repository", lambda _db: _UserRepo()
    )
    assert publisher._get_sender_name_sync(None, "user-1") == "Ada Lovelace"


def test_get_sender_name_sync_empty_first_name(monkeypatch):
    class _UserRepo:
        def get_by_id(self, _sender_id):
            return SimpleNamespace(first_name="", last_name="Doe")

    monkeypatch.setattr(
        publisher.RepositoryFactory, "create_user_repository", lambda _db: _UserRepo()
    )
    assert publisher._get_sender_name_sync(None, "user-1") == ""


def test_get_sender_name_sync_handles_exception(monkeypatch):
    monkeypatch.setattr(
        publisher.RepositoryFactory,
        "create_user_repository",
        lambda _db: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert publisher._get_sender_name_sync(None, "user-1") is None


@pytest.mark.asyncio
async def test_publish_typing_status_sends_to_other(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(publisher.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(
        publisher,
        "_get_conversation_participants_sync",
        lambda *_a, **_k: ["u1", "u2"],
    )

    await publisher.publish_typing_status(
        db=None,
        conversation_id="c1",
        user_id="u1",
        user_name="User",
        is_typing=True,
    )
    publish_mock.assert_awaited_once()
    assert publish_mock.await_args.args[0] == "u2"


@pytest.mark.asyncio
async def test_publish_typing_status_skips_when_empty(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(publisher.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(publisher, "_get_conversation_participants_sync", lambda *_a, **_k: [])

    await publisher.publish_typing_status(
        db=None, conversation_id="c1", user_id="u1", user_name="User", is_typing=True
    )
    publish_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_reaction_update_skips_missing_conversation(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(publisher.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(publisher, "_get_conversation_participants_sync", lambda *_a, **_k: [])

    await publisher.publish_reaction_update(
        db=None,
        conversation_id="c1",
        message_id="m1",
        user_id="u1",
        emoji=":)",
        action="added",
    )
    publish_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_reaction_update_sends_to_all(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(publisher.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(
        publisher, "_get_conversation_participants_sync", lambda *_a, **_k: ["u1", "u2"]
    )

    await publisher.publish_reaction_update(
        db=None,
        conversation_id="c1",
        message_id="m1",
        user_id="u1",
        emoji=":)",
        action="added",
    )
    assert publish_mock.await_count == 2


@pytest.mark.asyncio
async def test_publish_message_edited_sends_to_all(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(publisher.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(
        publisher,
        "_get_conversation_participants_sync",
        lambda *_a, **_k: ["u1", "u2"],
    )

    await publisher.publish_message_edited(
        db=None,
        conversation_id="c1",
        message_id="m1",
        new_content="new",
        editor_id="u1",
        edited_at=datetime.now(timezone.utc),
    )
    assert publish_mock.await_count == 2


@pytest.mark.asyncio
async def test_publish_message_edited_skips_missing_conversation(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(publisher.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(publisher, "_get_conversation_participants_sync", lambda *_a, **_k: [])

    await publisher.publish_message_edited(
        db=None,
        conversation_id="c1",
        message_id="m1",
        new_content="new",
        editor_id="u1",
        edited_at=datetime.now(timezone.utc),
    )
    publish_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_read_receipt_sends_to_other(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(publisher.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(
        publisher,
        "_get_conversation_participants_sync",
        lambda *_a, **_k: ["u1", "u2"],
    )

    await publisher.publish_read_receipt(
        db=None, conversation_id="c1", reader_id="u1", message_ids=["m1", "m2"]
    )
    publish_mock.assert_awaited_once()
    assert publish_mock.await_args.args[0] == "u2"


@pytest.mark.asyncio
async def test_publish_read_receipt_skips_empty_participants(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(publisher.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(publisher, "_get_conversation_participants_sync", lambda *_a, **_k: [])

    await publisher.publish_read_receipt(
        db=None, conversation_id="c1", reader_id="u1", message_ids=["m1"]
    )
    publish_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_message_deleted_skips_missing_conversation(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(publisher.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(publisher, "_get_conversation_participants_sync", lambda *_a, **_k: [])

    await publisher.publish_message_deleted(
        db=None, conversation_id="c1", message_id="m1", deleted_by="u1"
    )
    publish_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_message_deleted_sends_to_all(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(publisher.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(
        publisher, "_get_conversation_participants_sync", lambda *_a, **_k: ["u1", "u2"]
    )

    await publisher.publish_message_deleted(
        db=None, conversation_id="c1", message_id="m1", deleted_by="u1"
    )
    assert publish_mock.await_count == 2


@pytest.mark.asyncio
async def test_publish_message_edited_direct_empty_participants(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    await publisher.publish_message_edited_direct(
        participant_ids=[],
        conversation_id="c1",
        message_id="m1",
        new_content="hi",
        editor_id="u1",
        edited_at=datetime.now(timezone.utc),
    )
    publish_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_read_receipt_direct_sends(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    await publisher.publish_read_receipt_direct(
        participant_ids=["u1", "u2"],
        conversation_id="c1",
        reader_id="u1",
        message_ids=["m1", "m2"],
    )
    publish_mock.assert_awaited_once()
    assert publish_mock.await_args.args[0] == "u2"


@pytest.mark.asyncio
async def test_publish_message_edited_direct_sends(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    await publisher.publish_message_edited_direct(
        participant_ids=["u1", "u2"],
        conversation_id="c1",
        message_id="m1",
        new_content="hi",
        editor_id="u1",
        edited_at=datetime.now(timezone.utc),
    )
    assert publish_mock.await_count == 2


@pytest.mark.asyncio
async def test_publish_message_deleted_direct_sends(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    await publisher.publish_message_deleted_direct(
        participant_ids=["u1", "u2"],
        conversation_id="c1",
        message_id="m1",
        deleted_by="u1",
    )
    assert publish_mock.await_count == 2


@pytest.mark.asyncio
async def test_publish_message_deleted_direct_skips_no_participants(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    await publisher.publish_message_deleted_direct(
        participant_ids=[],
        conversation_id="c1",
        message_id="m1",
        deleted_by="u1",
    )
    publish_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_reaction_update_direct_sends(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    await publisher.publish_reaction_update_direct(
        participant_ids=["u1", "u2"],
        conversation_id="c1",
        message_id="m1",
        user_id="u1",
        emoji=":)",
        action="added",
    )
    assert publish_mock.await_count == 2


@pytest.mark.asyncio
async def test_publish_reaction_update_direct_skips_no_participants(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    await publisher.publish_reaction_update_direct(
        participant_ids=[],
        conversation_id="c1",
        message_id="m1",
        user_id="u1",
        emoji=":)",
        action="added",
    )
    publish_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_typing_status_direct_skips_no_participants(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    await publisher.publish_typing_status_direct(
        participant_ids=[], conversation_id="c1", user_id="u1", user_name="User"
    )
    publish_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_new_message_direct_skips_no_participants(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    await publisher.publish_new_message_direct(
        participant_ids=[],
        message_id="m1",
        content="hello",
        sender_id="u1",
        sender_name="Sender",
        conversation_id="c1",
        created_at=datetime.now(timezone.utc),
    )
    publish_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_publish_new_message_direct_system_sender(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    await publisher.publish_new_message_direct(
        participant_ids=["u1", "u2"],
        message_id="m1",
        content="system",
        sender_id=None,
        sender_name=None,
        conversation_id="c1",
        created_at=datetime.now(timezone.utc),
    )
    assert publish_mock.await_count == 2


@pytest.mark.asyncio
async def test_publish_new_message_system_sender_includes_all(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(publisher.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(
        publisher,
        "_get_conversation_participants_sync",
        lambda *_a, **_k: ["u1", "u2"],
    )

    await publisher.publish_new_message(
        db=None,
        message_id="m1",
        content="system",
        sender_id=None,
        conversation_id="c1",
        created_at=datetime.now(timezone.utc),
        sender_name=None,
    )
    assert publish_mock.await_count == 2


@pytest.mark.asyncio
async def test_publish_new_message_sender_name_provided_skips_lookup(monkeypatch):
    publish_mock = AsyncMock()
    monkeypatch.setattr(publisher, "publish_to_user", publish_mock)

    async def _to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(publisher.asyncio, "to_thread", _to_thread)
    monkeypatch.setattr(
        publisher,
        "_get_conversation_participants_sync",
        lambda *_a, **_k: ["u1", "u2"],
    )

    def _boom(*_args, **_kwargs):
        raise AssertionError("should not be called")

    monkeypatch.setattr(publisher, "_get_sender_name_sync", _boom)

    await publisher.publish_new_message(
        db=None,
        message_id="m1",
        content="hi",
        sender_id="u1",
        conversation_id="c1",
        created_at=datetime.now(timezone.utc),
        sender_name="Provided",
    )
    assert publish_mock.await_count == 2
