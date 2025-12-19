# backend/app/routes/v1/admin/search_config.py
"""Admin search configuration routes (v1)."""

from fastapi import APIRouter, Depends

from app.dependencies.permissions import require_permission
from app.models import User
from app.schemas.nl_search import (
    AdminSearchConfigResponse,
    AdminSearchConfigUpdate,
    ModelOption,
)
from app.services.search.config import (
    AVAILABLE_EMBEDDING_MODELS,
    AVAILABLE_PARSING_MODELS,
    get_search_config,
    reset_search_config,
    update_search_config,
)
from app.services.search.nl_search_service import (
    get_search_inflight_count,
    set_uncached_search_concurrency_limit,
)

router = APIRouter(tags=["admin-search-config"])


def _build_admin_search_config_response() -> AdminSearchConfigResponse:
    config = get_search_config()
    return AdminSearchConfigResponse(
        parsing_model=config.parsing_model,
        parsing_timeout_ms=config.parsing_timeout_ms,
        embedding_model=config.embedding_model,
        embedding_timeout_ms=config.embedding_timeout_ms,
        location_model=config.location_model,
        location_timeout_ms=config.location_timeout_ms,
        search_budget_ms=config.search_budget_ms,
        high_load_budget_ms=config.high_load_budget_ms,
        high_load_threshold=config.high_load_threshold,
        uncached_concurrency=config.uncached_concurrency,
        openai_max_retries=config.max_retries,
        current_in_flight_requests=0,
        available_parsing_models=[ModelOption(**m) for m in AVAILABLE_PARSING_MODELS],
        available_embedding_models=[ModelOption(**m) for m in AVAILABLE_EMBEDDING_MODELS],
    )


@router.get("/search-config", response_model=AdminSearchConfigResponse)
async def get_search_config_admin(
    _: User = Depends(require_permission("admin:read")),
) -> AdminSearchConfigResponse:
    response = _build_admin_search_config_response()
    response.current_in_flight_requests = await get_search_inflight_count()
    return response


@router.post("/search-config", response_model=AdminSearchConfigResponse)
async def update_search_config_admin(
    update: AdminSearchConfigUpdate,
    _: User = Depends(require_permission("admin:manage")),
) -> AdminSearchConfigResponse:
    config = update_search_config(
        parsing_model=update.parsing_model,
        parsing_timeout_ms=update.parsing_timeout_ms,
        embedding_timeout_ms=update.embedding_timeout_ms,
        location_model=update.location_model,
        location_timeout_ms=update.location_timeout_ms,
        max_retries=update.openai_max_retries,
        search_budget_ms=update.search_budget_ms,
        high_load_budget_ms=update.high_load_budget_ms,
        high_load_threshold=update.high_load_threshold,
        uncached_concurrency=update.uncached_concurrency,
    )

    if update.uncached_concurrency is not None:
        await set_uncached_search_concurrency_limit(update.uncached_concurrency)

    response = AdminSearchConfigResponse(
        parsing_model=config.parsing_model,
        parsing_timeout_ms=config.parsing_timeout_ms,
        embedding_model=config.embedding_model,
        embedding_timeout_ms=config.embedding_timeout_ms,
        location_model=config.location_model,
        location_timeout_ms=config.location_timeout_ms,
        search_budget_ms=config.search_budget_ms,
        high_load_budget_ms=config.high_load_budget_ms,
        high_load_threshold=config.high_load_threshold,
        uncached_concurrency=config.uncached_concurrency,
        openai_max_retries=config.max_retries,
        current_in_flight_requests=await get_search_inflight_count(),
        available_parsing_models=[ModelOption(**m) for m in AVAILABLE_PARSING_MODELS],
        available_embedding_models=[ModelOption(**m) for m in AVAILABLE_EMBEDDING_MODELS],
    )
    return response


@router.post("/search-config/reset", response_model=AdminSearchConfigResponse)
async def reset_search_config_admin(
    _: User = Depends(require_permission("admin:manage")),
) -> AdminSearchConfigResponse:
    config = reset_search_config()
    await set_uncached_search_concurrency_limit(config.uncached_concurrency)
    response = AdminSearchConfigResponse(
        parsing_model=config.parsing_model,
        parsing_timeout_ms=config.parsing_timeout_ms,
        embedding_model=config.embedding_model,
        embedding_timeout_ms=config.embedding_timeout_ms,
        location_model=config.location_model,
        location_timeout_ms=config.location_timeout_ms,
        search_budget_ms=config.search_budget_ms,
        high_load_budget_ms=config.high_load_budget_ms,
        high_load_threshold=config.high_load_threshold,
        uncached_concurrency=config.uncached_concurrency,
        openai_max_retries=config.max_retries,
        current_in_flight_requests=await get_search_inflight_count(),
        available_parsing_models=[ModelOption(**m) for m in AVAILABLE_PARSING_MODELS],
        available_embedding_models=[ModelOption(**m) for m in AVAILABLE_EMBEDDING_MODELS],
    )
    return response
