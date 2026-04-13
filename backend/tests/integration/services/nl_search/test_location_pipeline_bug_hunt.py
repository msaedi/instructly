from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.models.unresolved_location_query import UnresolvedLocationQuery
from app.services.search.nl_pipeline import location, postflight, preflight
from app.services.search.nl_pipeline.models import UnresolvedLocationInfo
from app.services.search.nl_search_service import NLSearchService
from app.services.search.query_parser import ParsedQuery
from app.services.search.request_budget import RequestBudget


def _make_search_cache() -> AsyncMock:
    cache = AsyncMock()
    cache.get_cached_response = AsyncMock(return_value=None)
    cache.get_cached_parsed_query = AsyncMock(return_value=None)
    cache.cache_response = AsyncMock(return_value=True)
    cache.cache_parsed_query = AsyncMock(return_value=True)
    return cache


@pytest.mark.asyncio
async def test_unresolved_out_of_market_query_from_location_stage_persists_for_analytics(
    db,
    test_instructor,
) -> None:
    service = NLSearchService(search_cache=_make_search_cache())
    parsed_query = ParsedQuery(
        original_query="violin lessons in Georgetown",
        service_query="violin lessons",
        location_text="Georgetown",
        location_type="neighborhood",
    )
    pre_data = preflight.run_pre_openai_burst_for_service(
        service,
        parsed_query.original_query,
        parsed_query=parsed_query,
        user_id=None,
        user_location=None,
    )
    unresolved = UnresolvedLocationInfo(
        normalized="georgetown",
        original_query=parsed_query.original_query,
    )
    assert pre_data.location_resolution is None

    with patch.object(
        location,
        "resolve_location_openai_for_service",
        AsyncMock(return_value=(location.ResolvedLocation.from_not_found(), None, unresolved)),
    ):
        location_resolution, location_llm_cache, unresolved_info = (
            await location.resolve_location_stage_for_service(
                service,
                parsed_query=parsed_query,
                pre_data=pre_data,
                user_location=None,
                budget=RequestBudget(total_ms=500),
                timer=None,
                force_skip_tier5=False,
                force_skip_tier4=False,
                force_skip_embedding=False,
                tier5_task=None,
                tier5_started_at=None,
            )
        )

    post = postflight.run_post_openai_burst_for_service(
        service,
        pre_data,
        parsed_query,
        query_embedding=None,
        location_resolution=location_resolution,
        location_llm_cache=location_llm_cache,
        unresolved_info=unresolved_info,
        user_location=None,
        limit=5,
    )

    assert post.total_candidates >= 0
    with postflight.database_module.get_db_session() as check_db:
        stored = (
            check_db.query(UnresolvedLocationQuery)
            .filter(UnresolvedLocationQuery.query_normalized == "georgetown")
            .first()
        )
        assert stored is not None
        assert parsed_query.original_query in list(stored.sample_original_queries or [])
