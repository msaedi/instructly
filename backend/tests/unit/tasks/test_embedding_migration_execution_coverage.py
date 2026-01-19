"""
Tests for embedding_migration.py execution paths - targeting uncovered lines.

Covers lines: 50, 55-112, 147, 152-205 (async task execution code paths).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMaintainServiceEmbeddingsTask:
    """Tests for maintain_service_embeddings task execution."""

    def test_task_calls_asyncio_run(self) -> None:
        """Test that maintain_service_embeddings calls asyncio.run (line 50)."""
        from app.tasks.embedding_migration import maintain_service_embeddings

        mock_result = {"updated": 5, "failed": 1}

        def mock_asyncio_run_handler(coro):
            coro.close()  # Close the coroutine to prevent "was never awaited" warning
            return mock_result

        with patch(
            "app.tasks.embedding_migration.asyncio.run", side_effect=mock_asyncio_run_handler
        ) as mock_asyncio_run:
            result = maintain_service_embeddings.run()

            mock_asyncio_run.assert_called_once()
            assert result == mock_result


class TestMaintainEmbeddingsAsync:
    """Tests for _maintain_embeddings_async function."""

    @pytest.mark.asyncio
    async def test_no_services_need_embedding(self) -> None:
        """Test when no services need embedding updates (lines 69-71)."""
        from app.tasks.embedding_migration import _maintain_embeddings_async

        mock_session = MagicMock()
        mock_cache = MagicMock()
        mock_embedding_service = MagicMock()
        mock_embedding_service.get_services_needing_embedding.return_value = []

        with patch("app.tasks.embedding_migration.SessionLocal") as mock_session_local, \
             patch("app.tasks.embedding_migration.CacheService") as mock_cache_class, \
             patch("app.tasks.embedding_migration.EmbeddingService") as mock_embed_class, \
             patch("app.tasks.embedding_migration._check_embedding_coverage"):
            mock_session_local.return_value = mock_session
            mock_cache_class.return_value = mock_cache
            mock_embed_class.return_value = mock_embedding_service

            result = await _maintain_embeddings_async()

            assert result == {"updated": 0, "failed": 0}
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_embedding_update(self) -> None:
        """Test successful embedding of services (lines 73-97)."""
        from app.tasks.embedding_migration import _maintain_embeddings_async

        mock_session = MagicMock()
        mock_cache = MagicMock()

        # Create mock services
        mock_service1 = MagicMock()
        mock_service1.id = "service-1"
        mock_service2 = MagicMock()
        mock_service2.id = "service-2"

        mock_embedding_service = MagicMock()
        # First call returns services, second returns empty (exit loop)
        mock_embedding_service.get_services_needing_embedding.side_effect = [
            [mock_service1, mock_service2],
            [],
        ]
        mock_embedding_service.embed_services_batch = AsyncMock(return_value={
            "service-1": [0.1, 0.2, 0.3],
            "service-2": [0.4, 0.5, 0.6],
        })
        mock_embedding_service.generate_embedding_text.return_value = "test text"
        mock_embedding_service.compute_text_hash.return_value = "hash123"
        mock_embedding_service.update_service_embedding.return_value = True

        with patch("app.tasks.embedding_migration.SessionLocal") as mock_session_local, \
             patch("app.tasks.embedding_migration.CacheService") as mock_cache_class, \
             patch("app.tasks.embedding_migration.EmbeddingService") as mock_embed_class, \
             patch("app.tasks.embedding_migration._check_embedding_coverage"):
            mock_session_local.return_value = mock_session
            mock_cache_class.return_value = mock_cache
            mock_embed_class.return_value = mock_embedding_service

            result = await _maintain_embeddings_async()

            assert result["updated"] == 2
            assert result["failed"] == 0
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_partial_embedding_failure(self) -> None:
        """Test when some embeddings fail (lines 91-96)."""
        from app.tasks.embedding_migration import _maintain_embeddings_async

        mock_session = MagicMock()
        mock_cache = MagicMock()

        # Create mock services
        mock_service1 = MagicMock()
        mock_service1.id = "service-1"
        mock_service2 = MagicMock()
        mock_service2.id = "service-2"

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_services_needing_embedding.side_effect = [
            [mock_service1, mock_service2],
            [],
        ]
        # Only return embedding for service-1 (service-2 will fail)
        mock_embedding_service.embed_services_batch = AsyncMock(return_value={
            "service-1": [0.1, 0.2, 0.3],
        })
        mock_embedding_service.generate_embedding_text.return_value = "test text"
        mock_embedding_service.compute_text_hash.return_value = "hash123"
        mock_embedding_service.update_service_embedding.return_value = True

        with patch("app.tasks.embedding_migration.SessionLocal") as mock_session_local, \
             patch("app.tasks.embedding_migration.CacheService") as mock_cache_class, \
             patch("app.tasks.embedding_migration.EmbeddingService") as mock_embed_class, \
             patch("app.tasks.embedding_migration._check_embedding_coverage"):
            mock_session_local.return_value = mock_session
            mock_cache_class.return_value = mock_cache
            mock_embed_class.return_value = mock_embedding_service

            result = await _maintain_embeddings_async()

            assert result["updated"] == 1
            assert result["failed"] == 1  # service-2 failed

    @pytest.mark.asyncio
    async def test_update_service_embedding_fails(self) -> None:
        """Test when update_service_embedding returns False (lines 91-94)."""
        from app.tasks.embedding_migration import _maintain_embeddings_async

        mock_session = MagicMock()
        mock_cache = MagicMock()

        mock_service = MagicMock()
        mock_service.id = "service-1"

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_services_needing_embedding.side_effect = [
            [mock_service],
            [],
        ]
        mock_embedding_service.embed_services_batch = AsyncMock(return_value={
            "service-1": [0.1, 0.2, 0.3],
        })
        mock_embedding_service.generate_embedding_text.return_value = "test text"
        mock_embedding_service.compute_text_hash.return_value = "hash123"
        mock_embedding_service.update_service_embedding.return_value = False  # Update fails

        with patch("app.tasks.embedding_migration.SessionLocal") as mock_session_local, \
             patch("app.tasks.embedding_migration.CacheService") as mock_cache_class, \
             patch("app.tasks.embedding_migration.EmbeddingService") as mock_embed_class, \
             patch("app.tasks.embedding_migration._check_embedding_coverage"):
            mock_session_local.return_value = mock_session
            mock_cache_class.return_value = mock_cache
            mock_embed_class.return_value = mock_embedding_service

            result = await _maintain_embeddings_async()

            assert result["updated"] == 0
            assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_exception_reraises(self) -> None:
        """Test that exceptions are re-raised after cleanup (lines 108-110)."""
        from app.tasks.embedding_migration import _maintain_embeddings_async

        mock_session = MagicMock()
        mock_cache = MagicMock()

        mock_embedding_service = MagicMock()
        mock_embedding_service.get_services_needing_embedding.side_effect = Exception("DB error")

        with patch("app.tasks.embedding_migration.SessionLocal") as mock_session_local, \
             patch("app.tasks.embedding_migration.CacheService") as mock_cache_class, \
             patch("app.tasks.embedding_migration.EmbeddingService") as mock_embed_class:
            mock_session_local.return_value = mock_session
            mock_cache_class.return_value = mock_cache
            mock_embed_class.return_value = mock_embedding_service

            with pytest.raises(Exception, match="DB error"):
                await _maintain_embeddings_async()

            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_session_closed_finally(self) -> None:
        """Test that session is always closed (line 112)."""
        from app.tasks.embedding_migration import _maintain_embeddings_async

        mock_session = MagicMock()
        mock_cache = MagicMock()
        mock_embedding_service = MagicMock()
        mock_embedding_service.get_services_needing_embedding.return_value = []

        with patch("app.tasks.embedding_migration.SessionLocal") as mock_session_local, \
             patch("app.tasks.embedding_migration.CacheService") as mock_cache_class, \
             patch("app.tasks.embedding_migration.EmbeddingService") as mock_embed_class, \
             patch("app.tasks.embedding_migration._check_embedding_coverage"):
            mock_session_local.return_value = mock_session
            mock_cache_class.return_value = mock_cache
            mock_embed_class.return_value = mock_embedding_service

            await _maintain_embeddings_async()

            mock_session.close.assert_called_once()


class TestBulkEmbedAllServicesTask:
    """Tests for bulk_embed_all_services task execution."""

    def test_task_calls_asyncio_run(self) -> None:
        """Test that bulk_embed_all_services calls asyncio.run (line 147)."""
        from app.tasks.embedding_migration import bulk_embed_all_services

        mock_result = {"updated": 100, "failed": 5}

        def mock_asyncio_run_handler(coro):
            coro.close()  # Close the coroutine to prevent "was never awaited" warning
            return mock_result

        with patch(
            "app.tasks.embedding_migration.asyncio.run", side_effect=mock_asyncio_run_handler
        ) as mock_asyncio_run:
            result = bulk_embed_all_services.run()

            mock_asyncio_run.assert_called_once()
            assert result == mock_result


class TestBulkEmbedAsync:
    """Tests for _bulk_embed_async function."""

    @pytest.mark.asyncio
    async def test_no_services_need_embedding(self) -> None:
        """Test when no services need bulk embedding (lines 164-166)."""
        from app.tasks.embedding_migration import _bulk_embed_async

        mock_session = MagicMock()
        mock_cache = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_all_services_missing_embedding.return_value = []

        with patch("app.tasks.embedding_migration.SessionLocal") as mock_session_local, \
             patch("app.tasks.embedding_migration.CacheService") as mock_cache_class, \
             patch("app.tasks.embedding_migration.ServiceCatalogRepository") as mock_repo_class, \
             patch("app.tasks.embedding_migration.EmbeddingService"):
            mock_session_local.return_value = mock_session
            mock_cache_class.return_value = mock_cache
            mock_repo_class.return_value = mock_repo

            result = await _bulk_embed_async()

            assert result == {"updated": 0, "failed": 0}
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_successful_bulk_embedding(self) -> None:
        """Test successful bulk embedding of services (lines 168-197)."""
        from app.tasks.embedding_migration import _bulk_embed_async

        mock_session = MagicMock()
        mock_cache = MagicMock()

        # Create mock services
        mock_services = []
        for i in range(3):
            svc = MagicMock()
            svc.id = f"service-{i}"
            mock_services.append(svc)

        mock_repo = MagicMock()
        mock_repo.get_all_services_missing_embedding.return_value = mock_services

        mock_embedding_service = MagicMock()
        mock_embedding_service.embed_services_batch = AsyncMock(return_value={
            "service-0": [0.1, 0.2],
            "service-1": [0.3, 0.4],
            "service-2": [0.5, 0.6],
        })
        mock_embedding_service.generate_embedding_text.return_value = "test text"
        mock_embedding_service.compute_text_hash.return_value = "hash123"
        mock_embedding_service.update_service_embedding.return_value = True

        with patch("app.tasks.embedding_migration.SessionLocal") as mock_session_local, \
             patch("app.tasks.embedding_migration.CacheService") as mock_cache_class, \
             patch("app.tasks.embedding_migration.ServiceCatalogRepository") as mock_repo_class, \
             patch("app.tasks.embedding_migration.EmbeddingService") as mock_embed_class:
            mock_session_local.return_value = mock_session
            mock_cache_class.return_value = mock_cache
            mock_repo_class.return_value = mock_repo
            mock_embed_class.return_value = mock_embedding_service

            result = await _bulk_embed_async()

            assert result["updated"] == 3
            assert result["failed"] == 0
            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_partial_bulk_failure(self) -> None:
        """Test when some bulk embeddings fail (lines 190-195)."""
        from app.tasks.embedding_migration import _bulk_embed_async

        mock_session = MagicMock()
        mock_cache = MagicMock()

        mock_services = []
        for i in range(2):
            svc = MagicMock()
            svc.id = f"service-{i}"
            mock_services.append(svc)

        mock_repo = MagicMock()
        mock_repo.get_all_services_missing_embedding.return_value = mock_services

        mock_embedding_service = MagicMock()
        # Only return embedding for first service
        mock_embedding_service.embed_services_batch = AsyncMock(return_value={
            "service-0": [0.1, 0.2],
        })
        mock_embedding_service.generate_embedding_text.return_value = "test text"
        mock_embedding_service.compute_text_hash.return_value = "hash123"
        mock_embedding_service.update_service_embedding.return_value = True

        with patch("app.tasks.embedding_migration.SessionLocal") as mock_session_local, \
             patch("app.tasks.embedding_migration.CacheService") as mock_cache_class, \
             patch("app.tasks.embedding_migration.ServiceCatalogRepository") as mock_repo_class, \
             patch("app.tasks.embedding_migration.EmbeddingService") as mock_embed_class:
            mock_session_local.return_value = mock_session
            mock_cache_class.return_value = mock_cache
            mock_repo_class.return_value = mock_repo
            mock_embed_class.return_value = mock_embedding_service

            result = await _bulk_embed_async()

            assert result["updated"] == 1
            assert result["failed"] == 1

    @pytest.mark.asyncio
    async def test_bulk_exception_reraises(self) -> None:
        """Test that exceptions are re-raised after cleanup (lines 201-203)."""
        from app.tasks.embedding_migration import _bulk_embed_async

        mock_session = MagicMock()
        mock_cache = MagicMock()
        mock_repo = MagicMock()
        mock_repo.get_all_services_missing_embedding.side_effect = Exception("Repo error")

        with patch("app.tasks.embedding_migration.SessionLocal") as mock_session_local, \
             patch("app.tasks.embedding_migration.CacheService") as mock_cache_class, \
             patch("app.tasks.embedding_migration.ServiceCatalogRepository") as mock_repo_class, \
             patch("app.tasks.embedding_migration.EmbeddingService"):
            mock_session_local.return_value = mock_session
            mock_cache_class.return_value = mock_cache
            mock_repo_class.return_value = mock_repo

            with pytest.raises(Exception, match="Repo error"):
                await _bulk_embed_async()

            mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_bulk_processes_in_batches(self) -> None:
        """Test that bulk embedding processes services in BATCH_SIZE batches."""
        from app.tasks.embedding_migration import BATCH_SIZE, _bulk_embed_async

        mock_session = MagicMock()
        mock_cache = MagicMock()

        # Create more services than BATCH_SIZE
        mock_services = []
        for i in range(BATCH_SIZE + 10):
            svc = MagicMock()
            svc.id = f"service-{i}"
            mock_services.append(svc)

        mock_repo = MagicMock()
        mock_repo.get_all_services_missing_embedding.return_value = mock_services

        mock_embedding_service = MagicMock()
        # Return embeddings for all services
        embeddings = {f"service-{i}": [0.1] for i in range(BATCH_SIZE + 10)}
        mock_embedding_service.embed_services_batch = AsyncMock(return_value=embeddings)
        mock_embedding_service.generate_embedding_text.return_value = "test text"
        mock_embedding_service.compute_text_hash.return_value = "hash123"
        mock_embedding_service.update_service_embedding.return_value = True

        with patch("app.tasks.embedding_migration.SessionLocal") as mock_session_local, \
             patch("app.tasks.embedding_migration.CacheService") as mock_cache_class, \
             patch("app.tasks.embedding_migration.ServiceCatalogRepository") as mock_repo_class, \
             patch("app.tasks.embedding_migration.EmbeddingService") as mock_embed_class:
            mock_session_local.return_value = mock_session
            mock_cache_class.return_value = mock_cache
            mock_repo_class.return_value = mock_repo
            mock_embed_class.return_value = mock_embedding_service

            result = await _bulk_embed_async()

            # Should process all services across multiple batches
            assert result["updated"] == BATCH_SIZE + 10
            # embed_services_batch should be called twice (one for each batch)
            assert mock_embedding_service.embed_services_batch.call_count == 2


class TestCheckEmbeddingCoverage:
    """Tests for _check_embedding_coverage function - already covered but verify behavior."""

    def test_high_missing_percentage_logs_warning(self) -> None:
        """Test warning log when >5% missing (lines 125-128)."""
        from app.tasks.embedding_migration import _check_embedding_coverage

        mock_session = MagicMock()
        mock_repo = MagicMock()
        mock_repo.count_active_services.return_value = 100
        mock_repo.count_services_missing_embedding.return_value = 10  # 10%

        with patch("app.tasks.embedding_migration.ServiceCatalogRepository") as mock_repo_class, \
             patch("app.tasks.embedding_migration.logger") as mock_logger:
            mock_repo_class.return_value = mock_repo

            _check_embedding_coverage(mock_session)

            mock_logger.warning.assert_called_once()
            assert "HIGH" in mock_logger.warning.call_args[0][0]

    def test_low_missing_percentage_logs_info(self) -> None:
        """Test info log when <=5% but >0 missing (lines 129-130)."""
        from app.tasks.embedding_migration import _check_embedding_coverage

        mock_session = MagicMock()
        mock_repo = MagicMock()
        mock_repo.count_active_services.return_value = 100
        mock_repo.count_services_missing_embedding.return_value = 3  # 3%

        with patch("app.tasks.embedding_migration.ServiceCatalogRepository") as mock_repo_class, \
             patch("app.tasks.embedding_migration.logger") as mock_logger:
            mock_repo_class.return_value = mock_repo

            _check_embedding_coverage(mock_session)

            mock_logger.info.assert_called()
            # Should contain "LOW"
            info_calls = [str(c) for c in mock_logger.info.call_args_list]
            assert any("LOW" in c for c in info_calls)

    def test_all_services_have_embeddings(self) -> None:
        """Test info log when all services have embeddings (lines 131-132)."""
        from app.tasks.embedding_migration import _check_embedding_coverage

        mock_session = MagicMock()
        mock_repo = MagicMock()
        mock_repo.count_active_services.return_value = 100
        mock_repo.count_services_missing_embedding.return_value = 0

        with patch("app.tasks.embedding_migration.ServiceCatalogRepository") as mock_repo_class, \
             patch("app.tasks.embedding_migration.logger") as mock_logger:
            mock_repo_class.return_value = mock_repo

            _check_embedding_coverage(mock_session)

            mock_logger.info.assert_called()
            info_calls = [str(c) for c in mock_logger.info.call_args_list]
            assert any("All" in c and "have embeddings" in c for c in info_calls)

    def test_zero_total_services(self) -> None:
        """Test handling when there are no services."""
        from app.tasks.embedding_migration import _check_embedding_coverage

        mock_session = MagicMock()
        mock_repo = MagicMock()
        mock_repo.count_active_services.return_value = 0
        mock_repo.count_services_missing_embedding.return_value = 0

        with patch("app.tasks.embedding_migration.ServiceCatalogRepository") as mock_repo_class, \
             patch("app.tasks.embedding_migration.logger") as mock_logger:
            mock_repo_class.return_value = mock_repo

            # Should not crash with division by zero
            _check_embedding_coverage(mock_session)

            # Should not log warning (division by zero avoided)
            mock_logger.warning.assert_not_called()
