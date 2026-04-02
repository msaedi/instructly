"""Taxonomy helpers for NL search post-processing."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple, cast

from app.repositories.taxonomy_filter_repository import TaxonomyFilterRepository
from app.schemas.nl_search import NLSearchContentFilterDefinition, NLSearchContentFilterOption
from app.services.search.nl_pipeline import runtime
from app.services.search.retriever import ServiceCandidate

TOP_MATCH_SUBCATEGORY_CANDIDATES = 5
TOP_MATCH_SUBCATEGORY_MIN_CONSENSUS = 2


def load_subcategory_filter_metadata(
    taxonomy_repository: object,
    subcategory_id: str,
    *,
    get_cached_value: Optional[Callable[[str], Tuple[bool, object]]] = None,
    set_cached_value: Optional[Callable[[str, object], None]] = None,
) -> Tuple[List[Dict[str, object]], Optional[str]]:
    """Return cached taxonomy filter definitions and subcategory name."""
    get_cached_value = get_cached_value or runtime._get_cached_subcategory_filter_value
    set_cached_value = set_cached_value or runtime._set_cached_subcategory_filter_value
    filters_cache_key = f"filters:{subcategory_id}"
    name_cache_key = f"name:{subcategory_id}"
    has_cached_filters, cached_filters = get_cached_value(filters_cache_key)
    has_cached_name, cached_name = get_cached_value(name_cache_key)
    if has_cached_filters and has_cached_name:
        name_value = str(cached_name) if cached_name is not None else None
        return list(cast(List[Dict[str, object]], cached_filters)), name_value
    repo = cast(TaxonomyFilterRepository, taxonomy_repository)
    subcategory_filters = repo.get_filters_for_subcategory(subcategory_id)
    subcategory_name = repo.get_subcategory_name(subcategory_id)
    set_cached_value(filters_cache_key, subcategory_filters)
    set_cached_value(name_cache_key, subcategory_name)
    return subcategory_filters, subcategory_name


def build_available_content_filters(
    filter_definitions: List[Dict[str, object]],
) -> List[NLSearchContentFilterDefinition]:
    """Convert repository taxonomy filter definitions to API metadata."""
    available_filters: List[NLSearchContentFilterDefinition] = []
    for raw_filter in filter_definitions:
        key = str(raw_filter.get("filter_key") or "").strip().lower()
        if not key:
            continue
        label = str(raw_filter.get("filter_display_name") or key).strip() or key
        filter_type = str(raw_filter.get("filter_type") or "multi_select").strip()
        options: List[NLSearchContentFilterOption] = []
        seen_values: set[str] = set()
        raw_options = raw_filter.get("options")
        if not isinstance(raw_options, list):
            continue
        for raw_option in raw_options:
            if not isinstance(raw_option, dict):
                continue
            raw_value = str(raw_option.get("value") or "").strip().lower()
            if not raw_value or raw_value in seen_values:
                continue
            seen_values.add(raw_value)
            display_name = str(raw_option.get("display_name") or "").strip()
            options.append(
                NLSearchContentFilterOption(value=raw_value, label=display_name or raw_value)
            )
        if not options:
            continue
        available_filters.append(
            NLSearchContentFilterDefinition(
                key=key,
                label=label,
                type=filter_type,
                options=options,
            )
        )
    return available_filters


def resolve_effective_subcategory_id(
    candidates: List[ServiceCandidate],
    explicit_subcategory_id: Optional[str] = None,
    top_match_subcategory_candidates: int = TOP_MATCH_SUBCATEGORY_CANDIDATES,
    top_match_subcategory_min_consensus: int = TOP_MATCH_SUBCATEGORY_MIN_CONSENSUS,
) -> Optional[str]:
    """Resolve subcategory context with explicit-param priority then consensus."""
    if explicit_subcategory_id:
        normalized = str(explicit_subcategory_id).strip()
        if normalized:
            return normalized
    top_candidates = candidates[:top_match_subcategory_candidates]
    candidate_subcategory_ids = [
        str(candidate.subcategory_id).strip()
        for candidate in top_candidates
        if candidate.subcategory_id
    ]
    if not candidate_subcategory_ids:
        return None
    top_subcategory_id = candidate_subcategory_ids[0]
    if len(candidate_subcategory_ids) == 1:
        return top_subcategory_id
    consensus_count = sum(1 for value in candidate_subcategory_ids if value == top_subcategory_id)
    if consensus_count >= top_match_subcategory_min_consensus:
        return top_subcategory_id
    return None
