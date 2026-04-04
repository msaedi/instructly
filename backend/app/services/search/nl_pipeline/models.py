"""Pipeline data models — stage handoff contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from app.schemas.nl_search import NLSearchContentFilterDefinition, StageStatus
from app.services.search.nl_pipeline.protocols import DBSessionFactory, LoggerLike

if TYPE_CHECKING:
    from app.repositories.filter_repository import FilterRepository
    from app.repositories.ranking_repository import RankingRepository
    from app.repositories.retriever_repository import RetrieverRepository
    from app.repositories.search_batch_repository import RegionLookup, SearchBatchRepository
    from app.repositories.taxonomy_filter_repository import TaxonomyFilterRepository
    from app.repositories.unresolved_location_query_repository import (
        UnresolvedLocationQueryRepository,
    )
    from app.services.search.filter_service import FilterResult, FilterService
    from app.services.search.location_resolver import LocationResolver, ResolvedLocation
    from app.services.search.query_parser import ParsedQuery
    from app.services.search.ranking_service import RankedResult, RankingResult, RankingService
    from app.services.search.retriever import PostgresRetriever, ServiceCandidate


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

    def end_stage(
        self,
        status: str = StageStatus.SUCCESS.value,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
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


@dataclass(frozen=True, slots=True)
class ParseAndTextSearchResult:
    parsed_query: ParsedQuery
    parse_latency_ms: int
    has_service_embeddings: bool
    text_results: Optional[Dict[str, Tuple[float, Dict[str, object]]]]
    text_latency_ms: int
    best_text_score: float
    require_text_match: bool
    skip_vector: bool


@dataclass(frozen=True, slots=True)
class PreLocationTiersResult:
    region_lookup: Optional[RegionLookup]
    location_resolution: Optional[ResolvedLocation]
    location_normalized: Optional[str]
    cached_alias_normalized: Optional[str]
    fuzzy_score: Optional[float]
    location_llm_candidates: List[str]


@dataclass(frozen=True, slots=True)
class LocationLLMCache:
    """LLM-derived alias cache payload to persist in DB burst."""

    normalized: str
    confidence: float
    region_ids: List[str]


@dataclass(frozen=True, slots=True)
class UnresolvedLocationInfo:
    """Unresolved location payload to persist in DB burst."""

    normalized: str
    original_query: str


@dataclass(frozen=True, slots=True)
class PostBurstInputs:
    pre_data: PreOpenAIData
    parsed_query: ParsedQuery
    query_embedding: Optional[List[float]]
    location_resolution: Optional[ResolvedLocation]
    location_llm_cache: Optional[LocationLLMCache]
    unresolved_info: Optional[UnresolvedLocationInfo]
    user_location: Optional[Tuple[float, float]]
    limit: int
    requester_timezone: Optional[str]
    taxonomy_filter_selections: Optional[Dict[str, List[str]]]
    subcategory_id: Optional[str]


@dataclass(frozen=True, slots=True)
class PostBurstDeps:
    get_db_session: DBSessionFactory
    search_batch_repository_cls: type[SearchBatchRepository]
    retriever: PostgresRetriever
    filter_service_cls: type[FilterService]
    ranking_service_cls: type[RankingService]
    filter_repository_cls: type[FilterRepository]
    ranking_repository_cls: type[RankingRepository]
    retriever_repository_cls: type[RetrieverRepository]
    taxonomy_filter_repository_cls: type[TaxonomyFilterRepository]
    unresolved_location_query_repository_cls: type[UnresolvedLocationQueryRepository]
    location_resolver_cls: type[LocationResolver]
    region_code: str
    text_top_k: int
    vector_top_k: int
    max_candidates: int
    logger: LoggerLike


@dataclass(frozen=True, slots=True)
class PostBurstCallbacks:
    compute_text_match_flags: Callable[
        [str, Dict[str, Tuple[float, Dict[str, object]]]],
        tuple[float, bool, bool],
    ]
    normalize_taxonomy_filter_selections: Callable[
        [Optional[Dict[str, List[str]]]],
        Dict[str, List[str]],
    ]
    resolve_effective_subcategory_id_fn: Callable[
        [List[ServiceCandidate], Optional[str]],
        Optional[str],
    ]
    load_subcategory_filter_metadata_fn: Callable[
        [TaxonomyFilterRepository, str],
        Tuple[List[Dict[str, object]], Optional[str]],
    ]
    build_available_content_filters_fn: Callable[
        [List[Dict[str, object]]],
        List[NLSearchContentFilterDefinition],
    ]
    select_instructor_ids_fn: Callable[[List[RankedResult], int], List[str]]
    distance_region_ids_fn: Callable[[Optional[ResolvedLocation]], Optional[List[str]]]
    extract_inferred_filters: Callable[..., Dict[str, List[str]]]


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
