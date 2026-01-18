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
