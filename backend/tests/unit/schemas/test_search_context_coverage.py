from __future__ import annotations

import pytest

from app.schemas.search_context import SearchUserContext


def test_search_context_requires_one_identifier() -> None:
    with pytest.raises(ValueError):
        SearchUserContext()

    with pytest.raises(ValueError):
        SearchUserContext(user_id="u1", guest_session_id="g1")


def test_search_context_helpers(monkeypatch) -> None:
    ctx = SearchUserContext.from_user("u1", session_id="s1")
    assert ctx.identifier == "user_u1"
    assert ctx.is_authenticated is True

    guest = SearchUserContext.from_guest("g1")
    assert guest.identifier == "guest_g1"
    assert guest.is_authenticated is False

    monkeypatch.setattr(
        "app.schemas.search_context.settings",
        type("Settings", (), {"search_history_max_per_user": "12"})(),
        raising=False,
    )

    assert ctx.search_limit == 12


def test_search_context_normalize_int() -> None:
    ctx = SearchUserContext.from_user("u1")

    assert ctx._normalize_int(None) == 0
    assert ctx._normalize_int("  ") == 0
    assert ctx._normalize_int("5") == 5
    assert ctx._normalize_int(3.2) == 3
    assert ctx._normalize_int("bad", default=7) == 7


def test_search_context_repository_kwargs_and_edge_normalization() -> None:
    ctx = SearchUserContext.from_guest("g1")
    assert ctx.to_repository_kwargs() == {"user_id": None, "guest_session_id": "g1"}

    assert ctx._normalize_int(float("nan"), default=4) == 4

    class _BadInt:
        def __int__(self):
            raise TypeError("boom")

    assert ctx._normalize_int(_BadInt(), default=9) == 9
