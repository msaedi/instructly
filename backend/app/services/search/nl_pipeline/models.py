"""Pipeline data models — stage handoff contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from app.schemas.nl_search import NLSearchContentFilterDefinition, StageStatus

if TYPE_CHECKING:
    from app.repositories.search_batch_repository import RegionLookup
    from app.services.search.filter_service import FilterResult
    from app.services.search.location_resolver import ResolvedLocation
    from app.services.search.query_parser import ParsedQuery
    from app.services.search.ranking_service import RankingResult
    from app.services.search.retriever import ServiceCandidate


@dataclass
class SearchMetrics:
    """Metrics collected during search execution."""

    total_start: float = 0
    parse_latency_ms: int = 0
    embed_latency_ms: int = 0
    retrieve_latency_ms: int = 0
    filter_latency_ms: int = 0
    rank_latency_ms: int = 0
    total_latency_ms: int = 0
    cache_hit: bool = False
    degraded: bool = False
    degradation_reasons: List[str] = field(default_factory=list)


@dataclass
class PipelineTimer:
    """Collect timing data for diagnostics."""

    stages: List[Dict[str, Any]] = field(default_factory=list)
    location_tiers: List[Dict[str, Any]] = field(default_factory=list)
    _current_stage_name: Optional[str] = None
    _current_stage_start: Optional[float] = None

    def start_stage(self, name: str) -> None:
        self._current_stage_name = name
        self._current_stage_start = time.perf_counter()

    def end_stage(self, status: str = "success", details: Optional[Dict[str, Any]] = None) -> None:
        if self._current_stage_start is None or self._current_stage_name is None:
            return
        duration_ms = int((time.perf_counter() - self._current_stage_start) * 1000)
        self.stages.append(
            {
                "name": self._current_stage_name,
                "duration_ms": max(0, duration_ms),
                "status": status,
                "details": details or {},
            }
        )
        self._current_stage_name = None
        self._current_stage_start = None

    def record_stage(
        self,
        name: str,
        duration_ms: int,
        status: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.stages.append(
            {
                "name": name,
                "duration_ms": max(0, int(duration_ms)),
                "status": status,
                "details": details if details else None,
            }
        )

    def skip_stage(self, name: str, reason: str) -> None:
        self.record_stage(name, 0, StageStatus.SKIPPED.value, {"reason": reason})

    def record_location_tier(
        self,
        *,
        tier: int,
        attempted: bool,
        status: str,
        duration_ms: int,
        result: Optional[str] = None,
        confidence: Optional[float] = None,
        details: Optional[str] = None,
    ) -> None:
        self.location_tiers.append(
            {
                "tier": tier,
                "attempted": attempted,
                "status": status,
                "duration_ms": max(0, int(duration_ms)),
                "result": result,
                "confidence": confidence,
                "details": details,
            }
        )


@dataclass
class PreOpenAIData:
    """DB-backed data collected before OpenAI calls."""

    parsed_query: ParsedQuery
    parse_latency_ms: int
    text_results: Optional[Dict[str, Tuple[float, Dict[str, Any]]]]
    text_latency_ms: int
    has_service_embeddings: bool
    best_text_score: float
    require_text_match: bool
    skip_vector: bool
    region_lookup: Optional[RegionLookup]
    location_resolution: Optional[ResolvedLocation]
    location_normalized: Optional[str]
    cached_alias_normalized: Optional[str]
    fuzzy_score: Optional[float]
    location_llm_candidates: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class LocationLLMCache:
    """LLM-derived alias cache payload to persist in DB burst."""

    normalized: str
    confidence: float
    region_ids: List[str]


@dataclass(frozen=True)
class UnresolvedLocationInfo:
    """Unresolved location payload to persist in DB burst."""

    normalized: str
    original_query: str


@dataclass
class PostOpenAIData:
    """DB-backed data collected after OpenAI calls."""

    filter_result: FilterResult
    ranking_result: RankingResult
    retrieval_candidates: List[ServiceCandidate]
    instructor_rows: List[Dict[str, Any]]
    distance_meters: Dict[str, float]
    text_latency_ms: int
    vector_latency_ms: int
    filter_latency_ms: int
    rank_latency_ms: int
    vector_search_used: bool
    total_candidates: int
    filter_failed: bool
    ranking_failed: bool
    skip_vector: bool
    inferred_filters: Dict[str, List[str]] = field(default_factory=dict)
    effective_taxonomy_filters: Dict[str, List[str]] = field(default_factory=dict)
    effective_subcategory_id: Optional[str] = None
    effective_subcategory_name: Optional[str] = None
    available_content_filters: List[NLSearchContentFilterDefinition] = field(default_factory=list)
