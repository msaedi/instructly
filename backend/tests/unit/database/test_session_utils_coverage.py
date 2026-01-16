from __future__ import annotations

from types import SimpleNamespace

from app.database import session_utils


def test_resolve_session_bind_prefers_get_bind() -> None:
    class DummySession:
        def get_bind(self):
            return "bind"

    assert session_utils.resolve_session_bind(DummySession()) == "bind"


def test_resolve_session_bind_uses_inspect(monkeypatch) -> None:
    class DummySession:
        def get_bind(self):
            return None

    dummy_bind = SimpleNamespace(dialect=SimpleNamespace(name="postgres"))
    monkeypatch.setattr(session_utils, "inspect", lambda _session: SimpleNamespace(bind=dummy_bind))

    assert session_utils.resolve_session_bind(DummySession()) is dummy_bind


def test_resolve_session_bind_handles_errors(monkeypatch) -> None:
    class DummySession:
        def get_bind(self):
            raise RuntimeError("boom")

    def _raise(_session):
        raise RuntimeError("inspect")

    monkeypatch.setattr(session_utils, "inspect", _raise)

    assert session_utils.resolve_session_bind(DummySession()) is None


def test_get_dialect_name_fallback(monkeypatch) -> None:
    class DummySession:
        def get_bind(self):
            return None

    monkeypatch.setattr(session_utils, "resolve_session_bind", lambda _session: None)
    assert session_utils.get_dialect_name(DummySession(), default="sqlite") == "sqlite"


def test_get_dialect_name_reads_dialect() -> None:
    class DummySession:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name="postgres"))

    assert session_utils.get_dialect_name(DummySession()) == "postgres"


def test_get_dialect_name_missing_name() -> None:
    class DummySession:
        def get_bind(self):
            return SimpleNamespace(dialect=SimpleNamespace(name=None))

    assert session_utils.get_dialect_name(DummySession(), default="mysql") == "mysql"
