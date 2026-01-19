"""
Tests for worker.py - targeting CI coverage gaps.

Tests verify that worker.py can be imported and is properly configured.
"""



class TestWorkerModuleImport:
    """Tests verifying worker.py can be imported successfully."""

    def test_worker_module_imports_successfully(self) -> None:
        """
        Verify that worker.py can be imported without errors.

        Previously had a broken import from app.core.logging which
        didn't exist. This test verifies the fix is in place.
        """
        # Should not raise any import errors
        import app.tasks.worker  # noqa: F401

    def test_worker_module_has_start_worker_function(self) -> None:
        """Test that worker module exposes start_worker function."""
        from app.tasks import worker

        assert hasattr(worker, "start_worker")
        assert callable(worker.start_worker)

    def test_worker_module_has_logger(self) -> None:
        """Test that worker module has a configured logger."""
        from app.tasks import worker

        assert hasattr(worker, "logger")
        assert worker.logger is not None


class TestWorkerModuleStructure:
    """Tests for worker.py structure."""

    def test_worker_file_exists(self) -> None:
        """Verify worker.py file exists."""
        from pathlib import Path

        worker_path = Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "worker.py"
        assert worker_path.exists(), f"worker.py not found at {worker_path}"

    def test_worker_defines_start_worker_function(self) -> None:
        """Verify worker.py contains start_worker function definition."""
        from pathlib import Path

        worker_path = Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "worker.py"
        content = worker_path.read_text()
        assert "def start_worker" in content

    def test_worker_imports_celery_app(self) -> None:
        """Verify worker.py imports celery_app."""
        from pathlib import Path

        worker_path = Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "worker.py"
        content = worker_path.read_text()
        assert "from app.tasks import celery_app" in content

    def test_worker_has_queue_configuration(self) -> None:
        """Verify worker.py has queue configuration."""
        from pathlib import Path

        worker_path = Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "worker.py"
        content = worker_path.read_text()
        # Should configure queues for email, notifications, analytics, etc.
        assert "celery" in content.lower() and "queue" in content.lower()

    def test_worker_uses_logging_basicconfig(self) -> None:
        """Verify worker.py uses logging.basicConfig instead of broken setup_logging."""
        from pathlib import Path

        worker_path = Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "worker.py"
        content = worker_path.read_text()
        # Should use logging.basicConfig
        assert "logging.basicConfig" in content
        # Should NOT import from non-existent app.core.logging
        assert "from app.core.logging import setup_logging" not in content


class TestWorkerConfiguration:
    """Tests for worker configuration."""

    def test_worker_module_imports_celery_worker(self) -> None:
        """Test that worker module imports celery.bin.worker."""
        from app.tasks import worker

        # Should have imported worker from celery.bin
        assert hasattr(worker, "worker") or "worker" in dir(worker)

    def test_worker_celery_app_is_accessible(self) -> None:
        """Test that celery_app is accessible via the worker module."""
        from app.tasks import worker

        assert hasattr(worker, "celery_app")
        assert worker.celery_app is not None


def test_start_worker_builds_options(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.tasks import worker as worker_mod

    captured = {}

    class DummyWorker:
        def __init__(self, app):
            captured["app"] = app

        def run(self, **kwargs):
            captured["kwargs"] = kwargs

    monkeypatch.setattr(worker_mod.worker, "worker", DummyWorker)
    monkeypatch.setattr(worker_mod.os, "uname", lambda: SimpleNamespace(nodename="testhost"))
    monkeypatch.setattr(worker_mod.os, "cpu_count", lambda: 8)
    monkeypatch.setenv("CELERY_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("CELERY_POOL", "solo")
    monkeypatch.setenv("CELERY_CONCURRENCY", "2")
    monkeypatch.setenv("CELERY_HOSTNAME", "custom@host")
    monkeypatch.setenv("CELERY_QUEUES", "celery,analytics")

    worker_mod.start_worker()

    assert captured["app"] == worker_mod.celery_app
    assert captured["kwargs"]["loglevel"] == "WARNING"
    assert captured["kwargs"]["pool"] == "solo"
    assert captured["kwargs"]["concurrency"] == 2
    assert captured["kwargs"]["hostname"] == "custom@host"
    assert captured["kwargs"]["queues"] == "celery,analytics"
