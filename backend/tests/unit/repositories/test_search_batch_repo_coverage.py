"""Unit coverage for SearchBatchRepository – uncovered L147,153,163,177."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.repositories.search_batch_repository import SearchBatchRepository


def _make_repo() -> tuple[SearchBatchRepository, MagicMock]:
    mock_db = MagicMock()
    with patch(
        "app.repositories.search_batch_repository.LocationResolutionRepository"
    ), patch("app.repositories.search_batch_repository.RetrieverRepository"):
        repo = SearchBatchRepository(mock_db)
    return repo, mock_db


class TestLoadRegionLookup:
    """L147,153,163,177: branches in load_region_lookup."""

    def test_skips_non_region_boundary_items(self) -> None:
        """L147: non-RegionBoundary items are skipped."""
        repo, mock_db = _make_repo()
        repo._location_repo = MagicMock()
        repo._location_repo.list_regions.return_value = ["not_a_region", 42, None]

        lookup = repo.load_region_lookup()
        assert lookup.region_names == []
        assert lookup.by_name == {}

    def test_skips_empty_region_name(self) -> None:
        """L153: region with empty name is skipped in by_name but not by_id."""
        from app.models.region_boundary import RegionBoundary

        repo, mock_db = _make_repo()
        region = MagicMock(spec=RegionBoundary)
        region.id = "reg-01"
        region.region_name = ""
        region.parent_region = None
        region.name_embedding = None

        repo._location_repo = MagicMock()
        repo._location_repo.list_regions.return_value = [region]

        lookup = repo.load_region_lookup()
        assert lookup.region_names == []
        assert "reg-01" in lookup.by_id

    def test_duplicate_region_name_skipped(self) -> None:
        """L153-155: duplicate region names not added twice."""
        from app.models.region_boundary import RegionBoundary

        repo, mock_db = _make_repo()

        r1 = MagicMock(spec=RegionBoundary)
        r1.id = "reg-01"
        r1.region_name = "SoHo"
        r1.parent_region = "Manhattan"
        r1.name_embedding = None

        r2 = MagicMock(spec=RegionBoundary)
        r2.id = "reg-02"
        r2.region_name = "SoHo"
        r2.parent_region = "Manhattan"
        r2.name_embedding = None

        repo._location_repo = MagicMock()
        repo._location_repo.list_regions.return_value = [r1, r2]

        lookup = repo.load_region_lookup()
        assert lookup.region_names == ["SoHo"]
        assert len(lookup.by_id) == 2

    def test_embedding_with_zero_norm_skipped(self) -> None:
        """L177: zero-norm embedding is skipped."""
        from app.models.region_boundary import RegionBoundary

        repo, mock_db = _make_repo()
        region = MagicMock(spec=RegionBoundary)
        region.id = "reg-zero"
        region.region_name = "ZeroNorm"
        region.parent_region = None
        region.name_embedding = [0.0, 0.0, 0.0]

        repo._location_repo = MagicMock()
        repo._location_repo.list_regions.return_value = [region]

        lookup = repo.load_region_lookup()
        assert len(lookup.embeddings) == 0

    def test_valid_embedding_included(self) -> None:
        """Valid embeddings are included."""
        from app.models.region_boundary import RegionBoundary

        repo, mock_db = _make_repo()
        region = MagicMock(spec=RegionBoundary)
        region.id = "reg-valid"
        region.region_name = "Tribeca"
        region.parent_region = "Manhattan"
        region.name_embedding = [0.5, 0.3, 0.1]

        repo._location_repo = MagicMock()
        repo._location_repo.list_regions.return_value = [region]

        lookup = repo.load_region_lookup()
        assert len(lookup.embeddings) == 1
        assert lookup.embeddings[0].region_name == "Tribeca"


class TestGetCachedLlmAlias:
    """Cover get_cached_llm_alias branches."""

    def test_returns_none_when_no_alias(self) -> None:
        repo, _ = _make_repo()
        repo._location_repo = MagicMock()
        repo._location_repo.find_cached_alias.return_value = None

        assert repo.get_cached_llm_alias("unknown") is None

    def test_returns_none_for_non_location_alias(self) -> None:
        repo, _ = _make_repo()
        repo._location_repo = MagicMock()
        repo._location_repo.find_cached_alias.return_value = "not a LocationAlias"

        assert repo.get_cached_llm_alias("whatever") is None


class TestDelegatedMethods:
    """Cover delegate methods to internal repos."""

    def test_has_service_embeddings(self) -> None:
        repo, _ = _make_repo()
        repo._retriever_repo = MagicMock()
        repo._retriever_repo.has_embeddings.return_value = True

        assert repo.has_service_embeddings() is True

    def test_get_best_fuzzy_score(self) -> None:
        repo, _ = _make_repo()
        repo._location_repo = MagicMock()
        repo._location_repo.get_best_fuzzy_score.return_value = 0.85

        assert repo.get_best_fuzzy_score("tribeca") == 0.85

    def test_get_fuzzy_candidate_names(self) -> None:
        repo, _ = _make_repo()
        repo._location_repo = MagicMock()
        repo._location_repo.list_fuzzy_region_names.return_value = ["Tribeca"]

        assert repo.get_fuzzy_candidate_names("trib") == ["Tribeca"]
