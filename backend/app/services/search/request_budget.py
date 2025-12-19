"""
Request time budget for progressive degradation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time
from typing import List


class DegradationLevel(Enum):
    NONE = "none"
    LIGHT = "light"
    MODERATE = "moderate"
    HEAVY = "heavy"
    CRITICAL = "critical"


@dataclass
class RequestBudget:
    """Track time budget for a search request."""

    total_ms: int = 500
    start_time: float = field(default_factory=time.perf_counter)
    skipped_operations: List[str] = field(default_factory=list)

    # Operation cost estimates (ms)
    COST_TIER5_LLM = 150
    COST_TIER4_EMBEDDING = 100
    COST_VECTOR_SEARCH = 80
    COST_HYDRATION = 50
    COST_BURST2 = 80

    @property
    def remaining_ms(self) -> int:
        elapsed = (time.perf_counter() - self.start_time) * 1000
        return max(0, self.total_ms - int(elapsed))

    @property
    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.start_time) * 1000)

    def can_afford(self, cost_ms: int, *, buffer_ms: int = 20) -> bool:
        return self.remaining_ms >= (cost_ms + buffer_ms)

    def can_afford_tier5(self) -> bool:
        return self.can_afford(self.COST_TIER5_LLM)

    def can_afford_tier4(self) -> bool:
        return self.can_afford(self.COST_TIER4_EMBEDDING)

    def can_afford_vector_search(self) -> bool:
        return self.can_afford(self.COST_VECTOR_SEARCH)

    def can_afford_full_burst2(self) -> bool:
        return self.can_afford(self.COST_BURST2)

    def skip(self, operation: str) -> None:
        if operation not in self.skipped_operations:
            self.skipped_operations.append(operation)

    def is_critical(self) -> bool:
        return self.remaining_ms < 100

    def is_exhausted(self) -> bool:
        return self.remaining_ms < 30

    @property
    def degradation_level(self) -> DegradationLevel:
        if not self.skipped_operations:
            return DegradationLevel.NONE
        if "vector_search" in self.skipped_operations or "embedding" in self.skipped_operations:
            return DegradationLevel.HEAVY
        if "tier5_llm" in self.skipped_operations:
            return DegradationLevel.LIGHT
        if "tier4_embedding" in self.skipped_operations:
            return DegradationLevel.LIGHT
        return DegradationLevel.MODERATE

    @property
    def is_degraded(self) -> bool:
        return bool(self.skipped_operations)

    @property
    def degradation_reasons(self) -> List[str]:
        return [f"budget_skip_{op}" for op in self.skipped_operations]
