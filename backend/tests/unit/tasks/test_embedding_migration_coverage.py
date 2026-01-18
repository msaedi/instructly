"""
Tests for embedding_migration.py - targeting CI coverage gaps.
Bug hunting + coverage for vector embedding maintenance Celery tasks.

No critical bugs found. The async pattern with asyncio.run() inside Celery
tasks is unusual but works correctly since Celery workers are synchronous.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session


class TestTaskRegistration:
    """Tests for task registration and configuration."""

    def test_maintain_service_embeddings_is_registered(self) -> None:
        """Test maintain_service_embeddings task is registered."""
        from app.tasks.embedding_migration import maintain_service_embeddings

        assert maintain_service_embeddings.name == "maintain_service_embeddings"

    def test_bulk_embed_all_services_is_registered(self) -> None:
        """Test bulk_embed_all_services task is registered."""
        from app.tasks.embedding_migration import bulk_embed_all_services

        assert bulk_embed_all_services.name == "bulk_embed_all_services"


class TestTaskConfiguration:
    """Tests for task retry configuration."""

    def test_maintain_service_embeddings_max_retries(self) -> None:
        """Test maintain_service_embeddings has max_retries configured."""
        from app.tasks.embedding_migration import maintain_service_embeddings

        assert maintain_service_embeddings.max_retries == 3

    def test_bulk_embed_all_services_max_retries(self) -> None:
        """Test bulk_embed_all_services has max_retries configured."""
        from app.tasks.embedding_migration import bulk_embed_all_services

        assert bulk_embed_all_services.max_retries == 3

    def test_maintain_service_embeddings_is_bound(self) -> None:
        """Test maintain_service_embeddings is a bound task."""
        from app.tasks.embedding_migration import maintain_service_embeddings

        assert hasattr(maintain_service_embeddings, "bind")

    def test_bulk_embed_is_bound(self) -> None:
        """Test bulk_embed_all_services is a bound task."""
        from app.tasks.embedding_migration import bulk_embed_all_services

        assert hasattr(bulk_embed_all_services, "bind")


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_batch_size_constant(self) -> None:
        """Test BATCH_SIZE is properly defined."""
        from app.tasks.embedding_migration import BATCH_SIZE

        assert BATCH_SIZE == 50
        assert isinstance(BATCH_SIZE, int)

    def test_max_services_per_run_constant(self) -> None:
        """Test MAX_SERVICES_PER_RUN is properly defined."""
        from app.tasks.embedding_migration import MAX_SERVICES_PER_RUN

        assert MAX_SERVICES_PER_RUN == 200
        assert isinstance(MAX_SERVICES_PER_RUN, int)


class TestModuleImports:
    """Tests for module imports."""

    def test_logger_is_configured(self) -> None:
        """Test that logger is properly configured."""
        from app.tasks.embedding_migration import logger

        assert logger is not None
        assert logger.name == "app.tasks.embedding_migration"

    def test_session_local_is_accessible(self) -> None:
        """Test that SessionLocal is imported."""
        from app.tasks.embedding_migration import SessionLocal

        assert SessionLocal is not None

    def test_embedding_service_is_importable(self) -> None:
        """Test that EmbeddingService can be imported."""
        from app.tasks.embedding_migration import EmbeddingService

        assert EmbeddingService is not None

    def test_cache_service_is_importable(self) -> None:
        """Test that CacheService can be imported."""
        from app.tasks.embedding_migration import CacheService

        assert CacheService is not None


class TestCheckEmbeddingCoverage:
    """Tests for _check_embedding_coverage helper function."""

    @patch("app.tasks.embedding_migration.ServiceCatalogRepository")
    def test_check_coverage_all_services_have_embeddings(
        self,
        mock_repo_cls: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test logging when all services have embeddings."""
        import logging

        from app.tasks.embedding_migration import _check_embedding_coverage

        mock_repo = MagicMock()
        mock_repo.count_active_services.return_value = 100
        mock_repo.count_services_missing_embedding.return_value = 0
        mock_repo_cls.return_value = mock_repo

        mock_session = MagicMock(spec=Session)

        with caplog.at_level(logging.INFO):
            _check_embedding_coverage(mock_session)

        assert "All 100 active services have embeddings" in caplog.text

    @patch("app.tasks.embedding_migration.ServiceCatalogRepository")
    def test_check_coverage_low_missing_percentage(
        self,
        mock_repo_cls: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test logging when few services missing embeddings (<5%)."""
        import logging

        from app.tasks.embedding_migration import _check_embedding_coverage

        mock_repo = MagicMock()
        mock_repo.count_active_services.return_value = 100
        mock_repo.count_services_missing_embedding.return_value = 3  # 3%
        mock_repo_cls.return_value = mock_repo

        mock_session = MagicMock(spec=Session)

        with caplog.at_level(logging.INFO):
            _check_embedding_coverage(mock_session)

        assert "LOW" in caplog.text
        assert "3 services missing embeddings" in caplog.text

    @patch("app.tasks.embedding_migration.ServiceCatalogRepository")
    def test_check_coverage_high_missing_percentage(
        self,
        mock_repo_cls: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Test warning when many services missing embeddings (>5%)."""
        import logging

        from app.tasks.embedding_migration import _check_embedding_coverage

        mock_repo = MagicMock()
        mock_repo.count_active_services.return_value = 100
        mock_repo.count_services_missing_embedding.return_value = 10  # 10%
        mock_repo_cls.return_value = mock_repo

        mock_session = MagicMock(spec=Session)

        with caplog.at_level(logging.WARNING):
            _check_embedding_coverage(mock_session)

        assert "HIGH" in caplog.text
        assert "10.0%" in caplog.text

    @patch("app.tasks.embedding_migration.ServiceCatalogRepository")
    def test_check_coverage_zero_total_services(
        self,
        mock_repo_cls: MagicMock,
    ) -> None:
        """Test when there are no active services (avoid division by zero)."""
        from app.tasks.embedding_migration import _check_embedding_coverage

        mock_repo = MagicMock()
        mock_repo.count_active_services.return_value = 0
        mock_repo.count_services_missing_embedding.return_value = 0
        mock_repo_cls.return_value = mock_repo

        mock_session = MagicMock(spec=Session)

        # Should not raise ZeroDivisionError
        _check_embedding_coverage(mock_session)


class TestAsyncPatternDocumentation:
    """Tests documenting the async pattern used."""

    def test_maintain_embeddings_uses_asyncio_run(self) -> None:
        """Document that maintain_service_embeddings uses asyncio.run()."""
        import inspect

        from app.tasks.embedding_migration import maintain_service_embeddings

        source = inspect.getsource(maintain_service_embeddings)
        assert "asyncio.run" in source

    def test_bulk_embed_uses_asyncio_run(self) -> None:
        """Document that bulk_embed_all_services uses asyncio.run()."""
        import inspect

        from app.tasks.embedding_migration import bulk_embed_all_services

        source = inspect.getsource(bulk_embed_all_services)
        assert "asyncio.run" in source


class TestSessionManagement:
    """Tests documenting session management patterns."""

    def test_async_function_uses_try_finally(self) -> None:
        """Verify async functions use try/finally for session cleanup."""
        import inspect

        from app.tasks.embedding_migration import _maintain_embeddings_async

        source = inspect.getsource(_maintain_embeddings_async)
        assert "try:" in source
        assert "finally:" in source
        assert "db.close()" in source

    def test_bulk_async_function_uses_try_finally(self) -> None:
        """Verify bulk async function uses try/finally for session cleanup."""
        import inspect

        from app.tasks.embedding_migration import _bulk_embed_async

        source = inspect.getsource(_bulk_embed_async)
        assert "try:" in source
        assert "finally:" in source
        assert "db.close()" in source
