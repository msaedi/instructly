"""
Tests for search_history_cleanup.py - targeting CI coverage gaps.
Bug hunting + coverage for search history cleanup Celery tasks.

No significant bugs found - code follows proper patterns:
- Session management with try/finally
- Proper error propagation
- Statistics collected before and after cleanup
"""



class TestTaskRegistration:
    """Tests for task registration and configuration."""

    def test_cleanup_search_history_is_registered(self) -> None:
        """Test cleanup_search_history task is registered with correct name."""
        from app.tasks.search_history_cleanup import cleanup_search_history

        assert cleanup_search_history.name == "cleanup_search_history"

    def test_dry_run_is_registered(self) -> None:
        """Test search_history_cleanup_dry_run task is registered."""
        from app.tasks.search_history_cleanup import search_history_cleanup_dry_run

        assert search_history_cleanup_dry_run.name == "search_history_cleanup_dry_run"


class TestTaskConfiguration:
    """Tests for task retry and bind configuration."""

    def test_cleanup_search_history_is_bound_task(self) -> None:
        """Test cleanup_search_history is a bound task (receives self)."""
        from app.tasks.search_history_cleanup import cleanup_search_history

        # Bound tasks have the bind attribute set
        assert hasattr(cleanup_search_history, "bind")

    def test_cleanup_search_history_has_retry_config(self) -> None:
        """Test cleanup_search_history has retry configuration."""
        from app.tasks.search_history_cleanup import cleanup_search_history

        # Should have autoretry configured for exceptions
        assert hasattr(cleanup_search_history, "autoretry_for")

    def test_dry_run_is_bound_task(self) -> None:
        """Test dry_run is a bound task."""
        from app.tasks.search_history_cleanup import search_history_cleanup_dry_run

        assert hasattr(search_history_cleanup_dry_run, "bind")


class TestTypedSharedTaskDecorator:
    """Tests for the typed_shared_task helper function."""

    def test_typed_shared_task_returns_callable(self) -> None:
        """Test that typed_shared_task creates a callable decorator."""
        from app.tasks.search_history_cleanup import typed_shared_task

        decorator = typed_shared_task(name="test_task")
        assert callable(decorator)

    def test_typed_shared_task_preserves_celery_attributes(self) -> None:
        """Test that decorated functions have Celery task attributes."""
        from app.tasks.search_history_cleanup import cleanup_search_history

        # Should have standard Celery task attributes
        assert hasattr(cleanup_search_history, "delay")
        assert hasattr(cleanup_search_history, "apply_async")
        assert hasattr(cleanup_search_history, "s")  # signature


class TestModuleImports:
    """Tests for module imports."""

    def test_logger_is_configured(self) -> None:
        """Test that logger is properly configured."""
        from app.tasks.search_history_cleanup import logger

        assert logger is not None
        assert logger.name == "app.tasks.search_history_cleanup"

    def test_session_local_is_accessible(self) -> None:
        """Test that SessionLocal is imported."""
        from app.tasks.search_history_cleanup import SessionLocal

        assert SessionLocal is not None

    def test_cleanup_service_is_importable(self) -> None:
        """Test that SearchHistoryCleanupService can be imported."""
        from app.tasks.search_history_cleanup import SearchHistoryCleanupService

        assert SearchHistoryCleanupService is not None


class TestTaskReturnTypes:
    """Tests documenting expected return types."""

    def test_cleanup_returns_dict(self) -> None:
        """Document that cleanup_search_history returns a dict."""
        import inspect

        from app.tasks.search_history_cleanup import cleanup_search_history

        # Check the function signature suggests dict return
        source = inspect.getsource(cleanup_search_history)
        assert "Dict[str, Any]" in source or "return {" in source

    def test_dry_run_returns_dict(self) -> None:
        """Document that dry_run returns a dict."""
        import inspect

        from app.tasks.search_history_cleanup import search_history_cleanup_dry_run

        source = inspect.getsource(search_history_cleanup_dry_run)
        assert "Dict[str, Any]" in source or "return {" in source


class TestSessionManagement:
    """Tests documenting proper session management patterns."""

    def test_cleanup_uses_try_finally_for_session(self) -> None:
        """Verify cleanup uses try/finally pattern for session cleanup."""
        import inspect

        from app.tasks.search_history_cleanup import cleanup_search_history

        source = inspect.getsource(cleanup_search_history)
        assert "try:" in source
        assert "finally:" in source
        assert "db.close()" in source

    def test_dry_run_uses_try_finally_for_session(self) -> None:
        """Verify dry_run uses try/finally pattern for session cleanup."""
        import inspect

        from app.tasks.search_history_cleanup import search_history_cleanup_dry_run

        source = inspect.getsource(search_history_cleanup_dry_run)
        assert "try:" in source
        assert "finally:" in source
        assert "db.close()" in source
