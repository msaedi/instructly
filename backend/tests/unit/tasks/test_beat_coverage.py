"""
Tests for beat.py - targeting CI coverage gaps.

Tests verify that beat.py can be imported and is properly configured.
"""



class TestBeatModuleImport:
    """Tests verifying beat.py can be imported successfully."""

    def test_beat_module_imports_successfully(self) -> None:
        """
        Verify that beat.py can be imported without errors.

        Previously had a broken import from app.core.logging which
        didn't exist. This test verifies the fix is in place.
        """
        # Should not raise any import errors
        import app.tasks.beat  # noqa: F401

    def test_beat_module_has_start_beat_function(self) -> None:
        """Test that beat module exposes start_beat function."""
        from app.tasks import beat

        assert hasattr(beat, "start_beat")
        assert callable(beat.start_beat)

    def test_beat_module_has_logger(self) -> None:
        """Test that beat module has a configured logger."""
        from app.tasks import beat

        assert hasattr(beat, "logger")
        assert beat.logger is not None


class TestBeatModuleStructure:
    """Tests for beat.py structure."""

    def test_beat_file_exists(self) -> None:
        """Verify beat.py file exists."""
        from pathlib import Path

        beat_path = Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "beat.py"
        assert beat_path.exists(), f"beat.py not found at {beat_path}"

    def test_beat_defines_start_beat_function(self) -> None:
        """Verify beat.py contains start_beat function definition."""
        from pathlib import Path

        beat_path = Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "beat.py"
        content = beat_path.read_text()
        assert "def start_beat" in content

    def test_beat_imports_celery_app(self) -> None:
        """Verify beat.py imports celery_app."""
        from pathlib import Path

        beat_path = Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "beat.py"
        content = beat_path.read_text()
        assert "from app.tasks import celery_app" in content

    def test_beat_imports_beat_schedule(self) -> None:
        """Verify beat.py imports CELERY_BEAT_SCHEDULE."""
        from pathlib import Path

        beat_path = Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "beat.py"
        content = beat_path.read_text()
        assert "CELERY_BEAT_SCHEDULE" in content

    def test_beat_uses_logging_basicconfig(self) -> None:
        """Verify beat.py uses logging.basicConfig instead of broken setup_logging."""
        from pathlib import Path

        beat_path = Path(__file__).parent.parent.parent.parent / "app" / "tasks" / "beat.py"
        content = beat_path.read_text()
        # Should use logging.basicConfig
        assert "logging.basicConfig" in content
        # Should NOT import from non-existent app.core.logging
        assert "from app.core.logging import setup_logging" not in content


class TestBeatConfiguration:
    """Tests for beat configuration."""

    def test_beat_module_imports_celery_beat(self) -> None:
        """Test that beat module imports celery.bin.beat."""
        from app.tasks import beat

        # Should have imported beat from celery.bin
        assert hasattr(beat, "beat") or "beat" in dir(beat)

    def test_beat_schedule_is_accessible(self) -> None:
        """Test that CELERY_BEAT_SCHEDULE is accessible via the module."""
        from app.tasks import beat

        assert hasattr(beat, "CELERY_BEAT_SCHEDULE")


class TestStartBeatExecution:
    """Tests for start_beat function execution paths (lines 40-64)."""

    def test_start_beat_configures_beat_schedule(self, monkeypatch) -> None:
        """Test that start_beat sets the beat schedule on celery_app."""
        from unittest.mock import MagicMock, patch

        from app.tasks import beat

        mock_beat_instance = MagicMock()
        mock_beat_cls = MagicMock(return_value=mock_beat_instance)

        # Mock the beat.beat class to avoid actually starting scheduler
        with patch.object(beat.beat, "beat", mock_beat_cls):
            # Also mock celery_app.conf to track schedule assignment
            mock_conf = MagicMock()
            mock_conf.beat_schedule = None

            with patch.object(beat, "celery_app") as mock_celery:
                mock_celery.conf = mock_conf

                beat.start_beat()

                # Verify beat schedule was set
                assert mock_conf.beat_schedule == beat.CELERY_BEAT_SCHEDULE
                mock_beat_instance.run.assert_called_once()

    def test_start_beat_logs_scheduled_tasks(self, monkeypatch, caplog) -> None:
        """Test that start_beat logs all scheduled tasks."""
        import logging
        from unittest.mock import MagicMock, patch

        from app.tasks import beat

        mock_beat_instance = MagicMock()
        mock_beat_cls = MagicMock(return_value=mock_beat_instance)

        with caplog.at_level(logging.INFO):
            with patch.object(beat.beat, "beat", mock_beat_cls):
                with patch.object(beat, "celery_app") as mock_celery:
                    mock_celery.conf = MagicMock()

                    beat.start_beat()

                    # Should log startup message
                    assert "Starting Celery beat scheduler" in caplog.text

    def test_start_beat_creates_beat_instance_with_celery_app(self, monkeypatch) -> None:
        """Test that start_beat creates beat instance with celery_app."""
        from unittest.mock import MagicMock, patch

        from app.tasks import beat

        mock_beat_instance = MagicMock()
        mock_beat_cls = MagicMock(return_value=mock_beat_instance)

        with patch.object(beat.beat, "beat", mock_beat_cls):
            with patch.object(beat, "celery_app") as mock_celery:
                mock_celery.conf = MagicMock()

                beat.start_beat()

                # Verify beat was created with the app
                mock_beat_cls.assert_called_once_with(app=mock_celery)

    def test_start_beat_runs_with_correct_options(self, monkeypatch) -> None:
        """Test that start_beat runs beat with correct options (lines 54-64)."""
        import os
        from unittest.mock import MagicMock, patch

        from app.tasks import beat

        mock_beat_instance = MagicMock()
        mock_beat_cls = MagicMock(return_value=mock_beat_instance)

        with patch.object(beat.beat, "beat", mock_beat_cls):
            with patch.object(beat, "celery_app") as mock_celery:
                mock_celery.conf = MagicMock()
                # Set a custom log level to test env var reading
                with patch.dict(os.environ, {"CELERY_LOG_LEVEL": "DEBUG"}):
                    beat.start_beat()

                    # Verify run was called with expected options
                    call_kwargs = mock_beat_instance.run.call_args[1]
                    assert call_kwargs["loglevel"] == "DEBUG"
                    assert call_kwargs["traceback"] is True
                    assert call_kwargs["scheduler"] == "celery.beat:PersistentScheduler"
                    assert call_kwargs["schedule_filename"] == "celerybeat-schedule"
                    assert call_kwargs["max_interval"] == 5
                    assert call_kwargs["sync_every"] == 10

    def test_start_beat_uses_default_log_level(self, monkeypatch) -> None:
        """Test that start_beat uses INFO log level by default."""
        import os
        from unittest.mock import MagicMock, patch

        from app.tasks import beat

        mock_beat_instance = MagicMock()
        mock_beat_cls = MagicMock(return_value=mock_beat_instance)

        with patch.object(beat.beat, "beat", mock_beat_cls):
            with patch.object(beat, "celery_app") as mock_celery:
                mock_celery.conf = MagicMock()
                # Ensure CELERY_LOG_LEVEL is not set
                env = os.environ.copy()
                env.pop("CELERY_LOG_LEVEL", None)
                with patch.dict(os.environ, env, clear=True):
                    beat.start_beat()

                    call_kwargs = mock_beat_instance.run.call_args[1]
                    assert call_kwargs["loglevel"] == "INFO"

    def test_start_beat_logs_task_count_and_schedules(self, caplog) -> None:
        """Test that start_beat logs the number of configured tasks."""
        import logging
        from unittest.mock import MagicMock, patch

        from app.tasks import beat

        mock_beat_instance = MagicMock()
        mock_beat_cls = MagicMock(return_value=mock_beat_instance)

        # Create a test schedule
        test_schedule = {
            "test-task-1": {"schedule": "every 10 seconds", "task": "app.tasks.test1"},
            "test-task-2": {"schedule": "crontab(0, 0)", "task": "app.tasks.test2"},
        }

        with caplog.at_level(logging.INFO):
            with patch.object(beat.beat, "beat", mock_beat_cls):
                with patch.object(beat, "celery_app") as mock_celery:
                    mock_celery.conf = MagicMock()
                    with patch.object(beat, "CELERY_BEAT_SCHEDULE", test_schedule):
                        beat.start_beat()

                        # Should log the task count
                        assert "Configured 2 periodic tasks" in caplog.text
