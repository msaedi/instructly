from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest

from app.core.enums import PermissionName
from app.core.exceptions import ForbiddenException, NotFoundException, ValidationException
from app.core.request_context import get_request_id
from app.models.conversation import Conversation
from app.repositories.message_repository import MessageRepository
from app.routes.v1 import messages as messages_routes
from app.services.permission_service import PermissionService


@pytest.fixture
def message_repo(db):
    return MessageRepository(db)


@pytest.fixture
def conversation(db, test_student, test_instructor_with_availability):
    conv = Conversation(
        student_id=test_student.id,
        instructor_id=test_instructor_with_availability.id,
    )
    db.add(conv)
    db.commit()
    return conv


def _grant_message_permissions(db, user_id: str) -> None:
    PermissionService(db).grant_permission(user_id, PermissionName.VIEW_MESSAGES.value)
    PermissionService(db).grant_permission(user_id, PermissionName.SEND_MESSAGES.value)
    db.commit()


def _create_message(db, repo: MessageRepository, conversation_id: str, sender_id: str) -> str:
    msg = repo.create_conversation_message(conversation_id, sender_id, "Hello")
    db.commit()
    return msg.id


def test_get_message_config(client):
    response = client.get("/api/v1/messages/config")
    assert response.status_code == 200
    assert "edit_window_minutes" in response.json()


def test_get_unread_count_success(
    client,
    db,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
    auth_headers_student,
):
    _grant_message_permissions(db, test_student.id)
    _create_message(db, message_repo, conversation.id, test_instructor_with_availability.id)

    response = client.get("/api/v1/messages/unread-count", headers=auth_headers_student)
    assert response.status_code == 200
    assert response.json()["unread_count"] == 1


@pytest.mark.asyncio
async def test_get_unread_count_error(test_student):
    class ExplodingService:
        def get_unread_count(self, _user_id):
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc:
        await messages_routes.get_unread_count(
            current_user=test_student,
            service=ExplodingService(),
        )
    assert exc.value.status_code == 500


def test_mark_messages_as_read_requires_input(
    client,
    db,
    test_student,
    auth_headers_student,
):
    _grant_message_permissions(db, test_student.id)
    response = client.post(
        "/api/v1/messages/mark-read",
        json={"message_ids": []},
        headers=auth_headers_student,
    )
    assert response.status_code == 422


def test_mark_messages_as_read_success(
    client,
    db,
    message_repo,
    conversation,
    test_student,
    test_instructor_with_availability,
    auth_headers_student,
    monkeypatch,
):
    _grant_message_permissions(db, test_student.id)
    _create_message(db, message_repo, conversation.id, test_instructor_with_availability.id)

    publish_mock = AsyncMock()
    monkeypatch.setattr(messages_routes, "publish_read_receipt_direct", publish_mock)

    response = client.post(
        "/api/v1/messages/mark-read",
        json={"conversation_id": conversation.id},
        headers=auth_headers_student,
    )
    assert response.status_code == 200
    assert response.json()["messages_marked"] == 1
    assert publish_mock.called


@pytest.mark.asyncio
async def test_mark_messages_as_read_no_publish(test_student):
    class StubService:
        def mark_messages_read_with_context(self, *_args):
            return SimpleNamespace(count=0, marked_message_ids=[], conversation_id=None)

    result = await messages_routes.mark_messages_as_read(
        messages_routes.MarkMessagesReadRequest(conversation_id=None, message_ids=["id"]),
        current_user=test_student,
        service=StubService(),
    )
    assert result.messages_marked == 0


@pytest.mark.asyncio
async def test_mark_messages_as_read_publish_error(monkeypatch, test_student):
    class StubService:
        def mark_messages_read_with_context(self, *_args):
            return SimpleNamespace(
                count=1,
                marked_message_ids=["msg"],
                conversation_id="conv",
                participant_ids=["u1", "u2"],
            )

    async def explode_publish(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(messages_routes, "publish_read_receipt_direct", explode_publish)

    result = await messages_routes.mark_messages_as_read(
        messages_routes.MarkMessagesReadRequest(conversation_id="conv"),
        current_user=test_student,
        service=StubService(),
    )
    assert result.messages_marked == 1


@pytest.mark.asyncio
async def test_mark_messages_as_read_error_branches(test_student):
    class ValidationService:
        def mark_messages_read_with_context(self, *_args):
            raise ValidationException("bad")

    class ForbiddenService:
        def mark_messages_read_with_context(self, *_args):
            raise ForbiddenException("no")

    class ErrorService:
        def mark_messages_read_with_context(self, *_args):
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc:
        await messages_routes.mark_messages_as_read(
            messages_routes.MarkMessagesReadRequest(conversation_id="conv"),
            current_user=test_student,
            service=ValidationService(),
        )
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await messages_routes.mark_messages_as_read(
            messages_routes.MarkMessagesReadRequest(conversation_id="conv"),
            current_user=test_student,
            service=ForbiddenService(),
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await messages_routes.mark_messages_as_read(
            messages_routes.MarkMessagesReadRequest(conversation_id="conv"),
            current_user=test_student,
            service=ErrorService(),
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_edit_message_success(
    db,
    message_repo,
    conversation,
    test_student,
    monkeypatch,
):
    _grant_message_permissions(db, test_student.id)
    msg_id = _create_message(db, message_repo, conversation.id, test_student.id)

    publish_mock = AsyncMock()
    monkeypatch.setattr(messages_routes, "publish_message_edited_direct", publish_mock)

    service = messages_routes.MessageService(db)
    response = await messages_routes.edit_message.__wrapped__(
        msg_id,
        messages_routes.EditMessageRequest(content="Updated"),
        current_user=test_student,
        service=service,
    )
    assert response.status_code == 204
    assert publish_mock.called


@pytest.mark.asyncio
async def test_edit_message_publish_failure(
    db,
    monkeypatch,
    test_student,
):
    service = messages_routes.MessageService(db)

    async def explode_publish(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(messages_routes, "publish_message_edited_direct", explode_publish)

    result = SimpleNamespace(
        conversation_id="conv",
        participant_ids=["u1", "u2"],
        edited_at=None,
    )
    monkeypatch.setattr(service, "edit_message_with_context", lambda *_args: result)

    response = await messages_routes.edit_message.__wrapped__(
        "msg",
        messages_routes.EditMessageRequest(content="Updated"),
        current_user=test_student,
        service=service,
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_edit_message_without_conversation(db, test_student, monkeypatch):
    service = messages_routes.MessageService(db)
    result = SimpleNamespace(conversation_id=None, participant_ids=None, edited_at=None)
    monkeypatch.setattr(service, "edit_message_with_context", lambda *_args: result)

    response = await messages_routes.edit_message.__wrapped__(
        "msg",
        messages_routes.EditMessageRequest(content="Updated"),
        current_user=test_student,
        service=service,
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_edit_message_error_branches(db, test_student):
    class ValidationService:
        def edit_message_with_context(self, *_args):
            raise ValidationException("bad")

    class ForbiddenService:
        def edit_message_with_context(self, *_args):
            raise ForbiddenException("no")

    class ErrorService:
        def edit_message_with_context(self, *_args):
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc:
        await messages_routes.edit_message.__wrapped__(
            "msg",
            messages_routes.EditMessageRequest(content="Updated"),
            current_user=test_student,
            service=ValidationService(),
        )
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await messages_routes.edit_message.__wrapped__(
            "msg",
            messages_routes.EditMessageRequest(content="Updated"),
            current_user=test_student,
            service=ForbiddenService(),
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await messages_routes.edit_message.__wrapped__(
            "msg",
            messages_routes.EditMessageRequest(content="Updated"),
            current_user=test_student,
            service=ErrorService(),
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_edit_message_not_found(
    db,
    test_student,
):
    _grant_message_permissions(db, test_student.id)
    service = messages_routes.MessageService(db)

    with pytest.raises(HTTPException) as exc:
        await messages_routes.edit_message.__wrapped__(
            "01JE5000000000000000000000",
            messages_routes.EditMessageRequest(content="Updated"),
            current_user=test_student,
            service=service,
        )
    assert exc.value.status_code == 404


def test_delete_message_expired(
    client,
    db,
    message_repo,
    conversation,
    test_student,
    auth_headers_student,
):
    _grant_message_permissions(db, test_student.id)
    msg_id = _create_message(db, message_repo, conversation.id, test_student.id)
    msg = message_repo.get_by_id(msg_id)
    assert msg is not None
    msg.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    db.commit()

    response = client.delete(f"/api/v1/messages/{msg_id}", headers=auth_headers_student)
    assert response.status_code == 400


def test_delete_message_success(
    client,
    db,
    message_repo,
    conversation,
    test_student,
    auth_headers_student,
    monkeypatch,
):
    _grant_message_permissions(db, test_student.id)
    msg_id = _create_message(db, message_repo, conversation.id, test_student.id)

    publish_mock = AsyncMock()
    monkeypatch.setattr(messages_routes, "publish_message_deleted_direct", publish_mock)

    response = client.delete(f"/api/v1/messages/{msg_id}", headers=auth_headers_student)
    assert response.status_code == 200
    assert publish_mock.called


@pytest.mark.asyncio
async def test_delete_message_result_not_found(test_student):
    class StubService:
        def delete_message_with_context(self, *_args):
            return SimpleNamespace(success=False)

    with pytest.raises(HTTPException) as exc:
        await messages_routes.delete_message(
            "missing",
            current_user=test_student,
            service=StubService(),
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_message_publish_warning(monkeypatch, test_student):
    class StubService:
        def delete_message_with_context(self, *_args):
            return SimpleNamespace(success=True, conversation_id=None, participant_ids=None)

    response = await messages_routes.delete_message(
        "msg",
        current_user=test_student,
        service=StubService(),
    )
    assert response.success is True

    async def explode_publish(**_kwargs):
        raise RuntimeError("boom")

    class PublishService:
        def delete_message_with_context(self, *_args):
            return SimpleNamespace(
                success=True, conversation_id="conv", participant_ids=["u1", "u2"]
            )

    monkeypatch.setattr(messages_routes, "publish_message_deleted_direct", explode_publish)
    response = await messages_routes.delete_message(
        "msg",
        current_user=test_student,
        service=PublishService(),
    )
    assert response.success is True


@pytest.mark.asyncio
async def test_delete_message_error_branches(test_student):
    class ForbiddenService:
        def delete_message_with_context(self, *_args):
            raise ForbiddenException("no")

    class ValidationService:
        def delete_message_with_context(self, *_args):
            raise ValidationException("bad")

    class NotFoundService:
        def delete_message_with_context(self, *_args):
            raise NotFoundException("missing")

    class ErrorService:
        def delete_message_with_context(self, *_args):
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc:
        await messages_routes.delete_message(
            "msg", current_user=test_student, service=ForbiddenService()
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await messages_routes.delete_message(
            "msg", current_user=test_student, service=ValidationService()
        )
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await messages_routes.delete_message(
            "msg", current_user=test_student, service=NotFoundService()
        )
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await messages_routes.delete_message(
            "msg", current_user=test_student, service=ErrorService()
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_reaction_routes(
    db,
    message_repo,
    conversation,
    test_student,
    monkeypatch,
):
    _grant_message_permissions(db, test_student.id)
    msg_id = _create_message(db, message_repo, conversation.id, test_student.id)

    publish_mock = AsyncMock()
    monkeypatch.setattr(messages_routes, "publish_reaction_update_direct", publish_mock)

    service = messages_routes.MessageService(db)
    response = await messages_routes.add_reaction.__wrapped__(
        msg_id,
        messages_routes.ReactionRequest(emoji="👍"),
        current_user=test_student,
        service=service,
    )
    assert response.status_code == 204

    response = await messages_routes.remove_reaction.__wrapped__(
        msg_id,
        messages_routes.ReactionRequest(emoji="👍"),
        current_user=test_student,
        service=service,
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_reaction_routes_error_branches(test_student, monkeypatch):
    class ForbiddenService:
        def add_reaction_with_context(self, *_args):
            raise ForbiddenException("no")

    class NotFoundService:
        def add_reaction_with_context(self, *_args):
            raise NotFoundException("missing")

    class ErrorService:
        def add_reaction_with_context(self, *_args):
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc:
        await messages_routes.add_reaction.__wrapped__(
            "msg",
            messages_routes.ReactionRequest(emoji="👍"),
            current_user=test_student,
            service=ForbiddenService(),
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await messages_routes.add_reaction.__wrapped__(
            "msg",
            messages_routes.ReactionRequest(emoji="👍"),
            current_user=test_student,
            service=NotFoundService(),
        )
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await messages_routes.add_reaction.__wrapped__(
            "msg",
            messages_routes.ReactionRequest(emoji="👍"),
            current_user=test_student,
            service=ErrorService(),
        )
    assert exc.value.status_code == 500

    async def explode_publish(**_kwargs):
        raise RuntimeError("boom")

    class PublishService:
        def add_reaction_with_context(self, *_args):
            return SimpleNamespace(conversation_id="conv", participant_ids=["u1"], action="added")

    monkeypatch.setattr(messages_routes, "publish_reaction_update_direct", explode_publish)
    response = await messages_routes.add_reaction.__wrapped__(
        "msg",
        messages_routes.ReactionRequest(emoji="👍"),
        current_user=test_student,
        service=PublishService(),
    )
    assert response.status_code == 204

    class NoConversationService:
        def add_reaction_with_context(self, *_args):
            return SimpleNamespace(conversation_id=None, participant_ids=None, action=None)

    response = await messages_routes.add_reaction.__wrapped__(
        "msg",
        messages_routes.ReactionRequest(emoji="👍"),
        current_user=test_student,
        service=NoConversationService(),
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_remove_reaction_error_branches(test_student, monkeypatch):
    class ForbiddenService:
        def remove_reaction_with_context(self, *_args):
            raise ForbiddenException("no")

    class NotFoundService:
        def remove_reaction_with_context(self, *_args):
            raise NotFoundException("missing")

    class ErrorService:
        def remove_reaction_with_context(self, *_args):
            raise RuntimeError("boom")

    with pytest.raises(HTTPException) as exc:
        await messages_routes.remove_reaction.__wrapped__(
            "msg",
            messages_routes.ReactionRequest(emoji="👍"),
            current_user=test_student,
            service=ForbiddenService(),
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await messages_routes.remove_reaction.__wrapped__(
            "msg",
            messages_routes.ReactionRequest(emoji="👍"),
            current_user=test_student,
            service=NotFoundService(),
        )
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await messages_routes.remove_reaction.__wrapped__(
            "msg",
            messages_routes.ReactionRequest(emoji="👍"),
            current_user=test_student,
            service=ErrorService(),
        )
    assert exc.value.status_code == 500

    async def explode_publish(**_kwargs):
        raise RuntimeError("boom")

    class PublishService:
        def remove_reaction_with_context(self, *_args):
            return SimpleNamespace(conversation_id="conv", participant_ids=["u1"])

    monkeypatch.setattr(messages_routes, "publish_reaction_update_direct", explode_publish)
    response = await messages_routes.remove_reaction.__wrapped__(
        "msg",
        messages_routes.ReactionRequest(emoji="👍"),
        current_user=test_student,
        service=PublishService(),
    )
    assert response.status_code == 204

    class NoConversationService:
        def remove_reaction_with_context(self, *_args):
            return SimpleNamespace(conversation_id=None, participant_ids=None)

    response = await messages_routes.remove_reaction.__wrapped__(
        "msg",
        messages_routes.ReactionRequest(emoji="👍"),
        current_user=test_student,
        service=NoConversationService(),
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_stream_user_messages_emits_events(
    db, message_repo, conversation, test_student, test_instructor_with_availability, monkeypatch
):
    _grant_message_permissions(db, test_student.id)
    first_id = _create_message(db, message_repo, conversation.id, test_student.id)
    _create_message(db, message_repo, conversation.id, test_instructor_with_availability.id)

    async def fake_create_sse_stream(*, user_id, missed_messages):
        yield {"event": "message", "data": "ok"}

    async def fake_ensure_db_health(_db):
        return None

    monkeypatch.setattr(messages_routes, "create_sse_stream", fake_create_sse_stream)
    monkeypatch.setattr(messages_routes, "ensure_db_health", fake_ensure_db_health)
    monkeypatch.setattr(
        messages_routes,
        "user_has_cached_permission",
        lambda user, perm: True,
    )

    request = SimpleNamespace(headers={"Last-Event-ID": first_id})

    async def is_disconnected():
        return False

    request.is_disconnected = is_disconnected

    response = await messages_routes.stream_user_messages.__wrapped__(request, test_student)
    events = [chunk async for chunk in response.body_iterator]
    assert events


@pytest.mark.asyncio
async def test_stream_user_messages_sets_request_id(monkeypatch, test_student):
    async def fake_create_sse_stream(*, user_id, missed_messages):
        yield {"event": "message", "data": "ok"}

    async def fake_ensure_db_health(_db):
        return None

    monkeypatch.setattr(messages_routes, "create_sse_stream", fake_create_sse_stream)
    monkeypatch.setattr(messages_routes, "ensure_db_health", fake_ensure_db_health)
    monkeypatch.setattr(
        messages_routes,
        "user_has_cached_permission",
        lambda user, perm: True,
    )

    request = SimpleNamespace(
        headers={"X-Request-ID": "req-123"},
        state=SimpleNamespace(),
    )

    async def is_disconnected():
        return True

    request.is_disconnected = is_disconnected

    response = await messages_routes.stream_user_messages.__wrapped__(request, test_student)
    assert request.state.request_id == "req-123"
    assert response.headers.get("X-Request-ID") == "req-123"


@pytest.mark.asyncio
async def test_stream_user_messages_cleans_request_context(monkeypatch, test_student):
    async def fake_create_sse_stream(*, user_id, missed_messages):
        yield {"event": "message", "data": "ok"}

    async def fake_ensure_db_health(_db):
        return None

    monkeypatch.setattr(messages_routes, "create_sse_stream", fake_create_sse_stream)
    monkeypatch.setattr(messages_routes, "ensure_db_health", fake_ensure_db_health)
    monkeypatch.setattr(
        messages_routes,
        "user_has_cached_permission",
        lambda user, perm: True,
    )

    request = SimpleNamespace(
        headers={"X-Request-ID": "req-456"},
        state=SimpleNamespace(),
    )

    async def is_disconnected():
        return False

    request.is_disconnected = is_disconnected

    response = await messages_routes.stream_user_messages.__wrapped__(request, test_student)
    events = [chunk async for chunk in response.body_iterator]
    assert events
    assert get_request_id() is None


@pytest.mark.asyncio
async def test_stream_user_messages_disconnects_early(monkeypatch, test_student):
    async def fake_create_sse_stream(*, user_id, missed_messages):
        yield {"event": "message", "data": "ok"}

    async def fake_ensure_db_health(_db):
        return None

    monkeypatch.setattr(messages_routes, "create_sse_stream", fake_create_sse_stream)
    monkeypatch.setattr(messages_routes, "ensure_db_health", fake_ensure_db_health)
    monkeypatch.setattr(
        messages_routes,
        "user_has_cached_permission",
        lambda user, perm: True,
    )

    request = SimpleNamespace(headers={})

    async def is_disconnected():
        return True

    request.is_disconnected = is_disconnected

    response = await messages_routes.stream_user_messages.__wrapped__(request, test_student)
    events = [chunk async for chunk in response.body_iterator]
    assert events == []


@pytest.mark.asyncio
async def test_stream_user_messages_permission_denied(monkeypatch, test_student):
    request = SimpleNamespace(headers={})

    async def is_disconnected():
        return False

    request.is_disconnected = is_disconnected

    monkeypatch.setattr(
        messages_routes,
        "user_has_cached_permission",
        lambda user, perm: False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await messages_routes.stream_user_messages.__wrapped__(request, test_student)

    assert exc_info.value.status_code == 403
