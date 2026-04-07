"""Diagnostics and UI message helpers for NL search responses."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from app.schemas.nl_search import (
    BudgetInfo,
    LocationResolutionInfo,
    LocationTierResult,
    PipelineStage,
    SearchDiagnostics,
)
from app.services.search import config as config_module
from app.services.search.config import SearchConfig

if TYPE_CHECKING:
    from app.services.search.location_resolver import ResolvedLocation
    from app.services.search.nl_pipeline.models import PipelineTimer, PostOpenAIData, PreOpenAIData
    from app.services.search.query_parser import ParsedQuery
    from app.services.search.request_budget import RequestBudget


def _candidate_label(candidate: object) -> str:
    if not isinstance(candidate, dict):
        return ""
    return str(candidate.get("display_name") or candidate.get("region_name") or "").strip()


def format_location_resolved(location_resolution: Optional[ResolvedLocation]) -> Optional[str]:
    """Format a human-friendly resolved location string for UI/debug."""
    if not location_resolution:
        return None
    if location_resolution.resolved:
        # Safe: callers set region_name via _candidate_logical_name in location_resolver.py,
        # which prefers display_name. If a future caller bypasses that, raw NTA names would leak here.
        resolved_name = location_resolution.region_name
        if resolved_name is None:
            resolved_name = location_resolution.borough
        return str(resolved_name) if resolved_name is not None else None
    if not (location_resolution.requires_clarification and location_resolution.candidates):
        return None
    candidate_names = [_candidate_label(candidate) for candidate in location_resolution.candidates]
    candidate_names = [name for name in candidate_names if name]
    if not candidate_names:
        return None
    ordered_unique_names: List[str] = []
    seen: set[str] = set()
    for name in candidate_names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered_unique_names.append(name)

    def _split(name: str) -> tuple[str, str]:
        if "-" in name:
            base, suffix = name.split("-", 1)
            return base.strip(), suffix.strip()
        if " (" in name and name.endswith(")"):
            base, rest = name.split(" (", 1)
            return base.strip(), rest[:-1].strip()
        return "", ""

    split_parts = [_split(name) for name in ordered_unique_names]
    prefixes = {prefix for prefix, suffix in split_parts if prefix and suffix}
    if prefixes and len(prefixes) == 1 and all(suffix for _, suffix in split_parts):
        prefix = next(iter(prefixes))
        suffixes = sorted({suffix for _, suffix in split_parts}, key=lambda value: value.lower())
        if not suffixes or [suffix.lower() for suffix in suffixes] == [prefix.lower()]:
            return prefix
        return f"{prefix} ({', '.join(suffixes)})"
    return ", ".join(ordered_unique_names[:5])


def generate_soft_filter_message(
    parsed: ParsedQuery,
    filter_stats: Dict[str, int],
    location_resolution: Optional[ResolvedLocation],
    location_resolved: Optional[str],
    *,
    relaxed_constraints: List[str],
    result_count: int,
) -> Optional[str]:
    """Generate a user-facing message when soft filtering/relaxation is used."""
    messages: List[str] = []
    if parsed.location_text:
        if location_resolution and location_resolution.not_found:
            messages.append(f"Couldn't find location '{parsed.location_text}'")
        elif filter_stats.get("after_location") == 0:
            messages.append(f"No instructors found in {location_resolved or parsed.location_text}")
    if (parsed.date or parsed.time_after) and filter_stats.get("after_availability") == 0:
        if parsed.date:
            messages.append(f"No availability on {parsed.date.strftime('%A, %b %d')}")
        else:
            messages.append("No availability matching your time constraints")
    if parsed.max_price is not None and filter_stats.get("after_price") == 0:
        messages.append(f"No instructors under ${parsed.max_price}")
    if not messages:
        messages.append("No exact matches")
    location_related = any(
        message.startswith("No instructors found in")
        or message.startswith("Couldn't find location")
        for message in messages
    ) or ("location" in relaxed_constraints)
    relaxed = [constraint for constraint in relaxed_constraints if constraint]
    relaxed_text = f"Relaxed: {', '.join(relaxed)}." if relaxed else None
    lead = (
        f"Showing {result_count} results from nearby areas."
        if result_count > 0 and location_related
        else f"Showing {result_count} results."
        if result_count > 0
        else "No results found."
    )
    parts = [lead, ". ".join(messages) + ".", relaxed_text]
    return " ".join(part for part in parts if part).strip()


def build_budget_diagnostics(
    *,
    budget: Optional[RequestBudget],
    get_search_config: Optional[Callable[[], SearchConfig]] = None,
) -> BudgetInfo:
    get_search_config = get_search_config or config_module.get_search_config
    if budget is None:
        fallback_budget = int(get_search_config().search_budget_ms)
        return BudgetInfo(
            initial_ms=fallback_budget,
            remaining_ms=fallback_budget,
            over_budget=False,
            skipped_operations=[],
            degradation_level="none",
        )
    return BudgetInfo(
        initial_ms=budget.total_ms,
        remaining_ms=budget.remaining_ms,
        over_budget=budget.is_over_budget,
        skipped_operations=list(budget.skipped_operations),
        degradation_level=budget.degradation_level.value,
    )


def build_candidate_flow_diagnostics(
    *,
    pre_data: Optional[PreOpenAIData],
    post_data: Optional[PostOpenAIData],
    candidates_flow: Dict[str, int],
    results_count: int,
) -> Dict[str, int]:
    merged = dict(candidates_flow)
    if merged.get("after_text_search") is None and pre_data is not None:
        merged["after_text_search"] = len(pre_data.text_results or {})
    if merged.get("after_vector_search") is None and post_data is not None:
        merged["after_vector_search"] = int(post_data.total_candidates)
    if merged.get("initial_candidates") is None and post_data is not None:
        merged["initial_candidates"] = int(post_data.total_candidates)
    if post_data is not None and post_data.filter_result.filter_stats:
        stats = post_data.filter_result.filter_stats
        for key, stat_key in {
            "after_location_filter": "after_location",
            "after_price_filter": "after_price",
            "after_availability_filter": "after_availability",
        }.items():
            if merged.get(key) is None:
                merged[key] = int(stats.get(stat_key) or 0)
    if merged.get("final_results") is None:
        merged["final_results"] = results_count
    return merged


def build_location_diagnostics(
    *,
    timer: PipelineTimer,
    parsed_query: Optional[ParsedQuery],
    location_resolution: Optional[ResolvedLocation],
) -> Optional[LocationResolutionInfo]:
    if not parsed_query or not parsed_query.location_text:
        return None
    resolved_name = None
    resolved_regions: Optional[List[str]] = None
    successful_tier: Optional[int] = None
    if location_resolution:
        resolved_name = location_resolution.region_name or location_resolution.borough
        if location_resolution.tier is not None:
            try:
                successful_tier = int(location_resolution.tier.value)
            except Exception:
                successful_tier = None
        if location_resolution.candidates:
            names = [_candidate_label(candidate) for candidate in location_resolution.candidates]
            names = [name for name in names if name]
            if names:
                resolved_regions = list(dict.fromkeys(names))
    return LocationResolutionInfo(
        query=parsed_query.location_text,
        resolved_name=resolved_name,
        resolved_regions=resolved_regions,
        successful_tier=successful_tier,
        tiers=[LocationTierResult(**tier) for tier in timer.location_tiers],
    )


def build_search_diagnostics(
    *,
    timer: PipelineTimer,
    budget: Optional[RequestBudget],
    parsed_query: Optional[ParsedQuery],
    pre_data: Optional[PreOpenAIData],
    post_data: Optional[PostOpenAIData],
    location_resolution: Optional[ResolvedLocation],
    query_embedding: Optional[List[float]],
    results_count: int,
    cache_hit: bool,
    parsing_mode: str,
    candidates_flow: Dict[str, int],
    get_search_config: Optional[Callable[[], SearchConfig]] = None,
    total_latency_ms: Optional[int] = None,
) -> SearchDiagnostics:
    get_search_config = get_search_config or config_module.get_search_config
    budget_info = build_budget_diagnostics(budget=budget, get_search_config=get_search_config)
    merged_candidates = build_candidate_flow_diagnostics(
        pre_data=pre_data,
        post_data=post_data,
        candidates_flow=candidates_flow,
        results_count=results_count,
    )
    location_info = build_location_diagnostics(
        timer=timer,
        parsed_query=parsed_query,
        location_resolution=location_resolution,
    )
    return SearchDiagnostics(
        total_latency_ms=int(total_latency_ms)
        if total_latency_ms is not None
        else (budget.elapsed_ms if budget else 0),
        pipeline_stages=[PipelineStage(**stage) for stage in timer.stages],
        budget=budget_info,
        location_resolution=location_info,
        initial_candidates=int(merged_candidates.get("initial_candidates") or 0),
        after_text_search=int(merged_candidates.get("after_text_search") or 0),
        after_vector_search=int(merged_candidates.get("after_vector_search") or 0),
        after_location_filter=int(merged_candidates.get("after_location_filter") or 0),
        after_price_filter=int(merged_candidates.get("after_price_filter") or 0),
        after_availability_filter=int(merged_candidates.get("after_availability_filter") or 0),
        final_results=int(merged_candidates.get("final_results") or 0),
        cache_hit=cache_hit,
        parsing_mode=parsing_mode,
        embedding_used=bool(query_embedding),
        vector_search_used=bool(post_data.vector_search_used) if post_data else False,
    )


def build_candidates_flow(include_diagnostics: bool) -> Dict[str, int]:
    if not include_diagnostics:
        return {}
    return {
        "initial_candidates": 0,
        "after_text_search": 0,
        "after_vector_search": 0,
        "after_location_filter": 0,
        "after_price_filter": 0,
        "after_availability_filter": 0,
        "final_results": 0,
    }
