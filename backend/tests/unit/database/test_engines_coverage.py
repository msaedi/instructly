"""Unit coverage for app.database.engines – uncovered L70-71,77,91,202,204."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.database.engines import (
    _build_connect_args,
    _create_engine,
    _pool_recycle_seconds,
    _should_require_ssl,
    get_engine_for_role,
)


class TestShouldRequireSsl:
    """L70-71: URL parsing error and localhost detection."""

    def test_supabase_requires_ssl(self) -> None:
        assert _should_require_ssl("postgresql://db.abc123.supabase.co:5432/postgres") is True

    def test_supabase_net_requires_ssl(self) -> None:
        assert _should_require_ssl("postgresql://host.supabase.net:5432/db") is True

    def test_localhost_no_ssl(self) -> None:
        assert _should_require_ssl("postgresql://localhost:5432/db") is False

    def test_invalid_url_no_ssl(self) -> None:
        """L70-71: Exception in urlparse hostname -> no SSL."""
        # This exercises the except branch
        assert _should_require_ssl("") is False

    def test_plain_host_no_ssl(self) -> None:
        assert _should_require_ssl("postgresql://mydbhost:5432/db") is False


class TestBuildConnectArgs:
    """L77: SSL stripped for non-Supabase URLs."""

    def test_supabase_url_includes_sslmode(self) -> None:
        args = _build_connect_args(
            db_url="postgresql://db.abc123.supabase.co:5432/db",
            connect_timeout=5,
        )
        assert args["sslmode"] == "require"
        assert args["connect_timeout"] == 5
        assert "options" not in args

    def test_localhost_url_strips_sslmode(self) -> None:
        args = _build_connect_args(
            db_url="postgresql://localhost:5432/db",
            connect_timeout=10,
        )
        assert "sslmode" not in args
        assert args["connect_timeout"] == 10
        assert "options" not in args

    def test_create_engine_registers_statement_timeout_listener(self) -> None:
        fake_engine = MagicMock()
        listeners: list[tuple[str, object]] = []
        dbapi_connection = MagicMock()
        cursor = dbapi_connection.cursor.return_value

        def _capture_listener(_target, name, fn):
            listeners.append((name, fn))

        with (
            patch("app.database.engines.settings") as mock_settings,
            patch("app.database.engines.create_engine", return_value=fake_engine),
            patch("app.database.engines._add_pool_events"),
            patch("app.database.engines._pool_recycle_seconds", return_value=45),
            patch("app.database.engines.event.listen", side_effect=_capture_listener),
        ):
            mock_settings.get_database_url.return_value = "postgresql://db.supabase.net/postgres"
            _create_engine(
                pool_size=1,
                max_overflow=2,
                pool_timeout=3,
                statement_timeout_ms=12345,
                connect_timeout=7,
                pool_name="API",
            )

        assert listeners
        assert len(listeners) == 1
        assert listeners[0][0] == "connect"
        listener = listeners[0][1]
        listener(dbapi_connection, MagicMock())
        cursor.execute.assert_called_once_with("SET statement_timeout = 12345")
        cursor.close.assert_called_once()


class TestPoolRecycleSeconds:
    """L91: production vs dev pool_recycle."""

    def test_production_recycle(self) -> None:
        with patch("app.database.engines.settings") as mock_settings:
            mock_settings.environment = "production"
            assert _pool_recycle_seconds() == 45

    def test_dev_recycle(self) -> None:
        with patch("app.database.engines.settings") as mock_settings:
            mock_settings.environment = "development"
            assert _pool_recycle_seconds() == 30


class TestGetEngineForRole:
    """L202,204: role routing."""

    def test_worker_role(self) -> None:
        with patch("app.database.engines.get_worker_engine") as mock_worker:
            mock_worker.return_value = MagicMock()
            get_engine_for_role("worker")
            mock_worker.assert_called_once()

    def test_scheduler_role(self) -> None:
        with patch("app.database.engines.get_scheduler_engine") as mock_sched:
            mock_sched.return_value = MagicMock()
            get_engine_for_role("scheduler")
            mock_sched.assert_called_once()

    def test_api_role_default(self) -> None:
        with patch("app.database.engines.get_api_engine") as mock_api:
            mock_api.return_value = MagicMock()
            get_engine_for_role("api")
            mock_api.assert_called_once()

    def test_none_role_defaults_to_api(self) -> None:
        with patch("app.database.engines.get_api_engine") as mock_api, patch.dict(
            "os.environ", {"DB_POOL_ROLE": ""}
        ):
            mock_api.return_value = MagicMock()
            get_engine_for_role(None)
            mock_api.assert_called_once()

    def test_env_var_role(self) -> None:
        with patch("app.database.engines.get_worker_engine") as mock_worker, patch.dict(
            "os.environ", {"DB_POOL_ROLE": "worker"}
        ):
            mock_worker.return_value = MagicMock()
            get_engine_for_role(None)
            mock_worker.assert_called_once()
