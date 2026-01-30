# backend/tests/unit/services/search/test_request_budget_coverage.py
"""
Coverage tests for request_budget.py.
Targets missed lines: 61, 68, 81-85
"""
from __future__ import annotations

import time

from app.services.search.request_budget import DegradationLevel, RequestBudget


class TestRequestBudgetBasics:
    """Test basic budget functionality."""

    def test_initial_remaining_ms(self) -> None:
        """Fresh budget should have full time remaining."""
        budget = RequestBudget(total_ms=500)
        assert budget.remaining_ms > 0
        assert budget.remaining_ms <= 500

    def test_elapsed_ms_increases(self) -> None:
        """elapsed_ms should increase over time."""
        budget = RequestBudget(total_ms=500)
        time.sleep(0.01)  # 10ms
        assert budget.elapsed_ms >= 10

    def test_remaining_ms_decreases(self) -> None:
        """remaining_ms should decrease as time passes."""
        budget = RequestBudget(total_ms=500)
        initial = budget.remaining_ms
        time.sleep(0.01)
        assert budget.remaining_ms < initial

    def test_remaining_ms_floors_at_zero(self) -> None:
        """remaining_ms should not go negative."""
        budget = RequestBudget(total_ms=1)  # Very small budget
        time.sleep(0.01)  # Wait longer than budget
        assert budget.remaining_ms == 0


class TestCanAfford:
    """Test budget affordability checks."""

    def test_can_afford_when_budget_sufficient(self) -> None:
        """Should return True when budget is sufficient."""
        budget = RequestBudget(total_ms=500)
        assert budget.can_afford(100) is True

    def test_can_afford_respects_buffer(self) -> None:
        """Should respect buffer_ms parameter."""
        budget = RequestBudget(total_ms=100)
        # Can't afford if cost + buffer > remaining
        # With default buffer of 20, 100 + 20 = 120 > 100
        assert budget.can_afford(100) is False
        assert budget.can_afford(70) is True  # 70 + 20 = 90 < ~100

    def test_can_afford_tier5(self) -> None:
        """Test tier5 affordability check."""
        budget = RequestBudget(total_ms=500)
        assert budget.can_afford_tier5() is True

        small_budget = RequestBudget(total_ms=100)
        assert small_budget.can_afford_tier5() is False  # 150 + 20 > 100

    def test_can_afford_tier4(self) -> None:
        """Test tier4 affordability check."""
        budget = RequestBudget(total_ms=500)
        assert budget.can_afford_tier4() is True

        small_budget = RequestBudget(total_ms=50)
        assert small_budget.can_afford_tier4() is False

    def test_can_afford_vector_search(self) -> None:
        """Test vector search affordability."""
        budget = RequestBudget(total_ms=500)
        assert budget.can_afford_vector_search() is True

        small_budget = RequestBudget(total_ms=50)
        assert small_budget.can_afford_vector_search() is False

    def test_can_afford_full_burst2(self) -> None:
        """Test burst2 affordability."""
        budget = RequestBudget(total_ms=500)
        assert budget.can_afford_full_burst2() is True

        small_budget = RequestBudget(total_ms=50)
        assert small_budget.can_afford_full_burst2() is False


class TestSkipOperations:
    """Test operation skipping and tracking."""

    def test_skip_adds_to_list(self) -> None:
        """Skip should add operation to skipped_operations."""
        budget = RequestBudget()
        budget.skip("tier5_llm")
        assert "tier5_llm" in budget.skipped_operations

    def test_skip_no_duplicates(self) -> None:
        """Skip should not add duplicates."""
        budget = RequestBudget()
        budget.skip("tier5_llm")
        budget.skip("tier5_llm")
        budget.skip("tier5_llm")
        assert budget.skipped_operations.count("tier5_llm") == 1

    def test_skip_multiple_operations(self) -> None:
        """Can skip multiple different operations."""
        budget = RequestBudget()
        budget.skip("tier5_llm")
        budget.skip("tier4_embedding")
        budget.skip("vector_search")
        assert len(budget.skipped_operations) == 3


class TestBudgetStatus:
    """Test budget status checks."""

    def test_is_critical_when_low(self) -> None:
        """is_critical should be True when remaining < 100ms."""
        budget = RequestBudget(total_ms=50)
        assert budget.is_critical() is True

        good_budget = RequestBudget(total_ms=500)
        assert good_budget.is_critical() is False

    def test_is_exhausted_when_very_low(self) -> None:
        """is_exhausted should be True when remaining < 30ms."""
        budget = RequestBudget(total_ms=20)
        assert budget.is_exhausted() is True

        ok_budget = RequestBudget(total_ms=500)
        assert ok_budget.is_exhausted() is False

    def test_is_over_budget(self) -> None:
        """is_over_budget should be True when elapsed > total."""
        budget = RequestBudget(total_ms=1)
        time.sleep(0.01)
        assert budget.is_over_budget is True

        fresh_budget = RequestBudget(total_ms=5000)
        assert fresh_budget.is_over_budget is False


class TestDegradationLevel:
    """Test degradation level calculation - Lines 74-85."""

    def test_degradation_none_when_fresh(self) -> None:
        """No degradation when budget is good and nothing skipped."""
        budget = RequestBudget(total_ms=500)
        assert budget.degradation_level == DegradationLevel.NONE

    def test_degradation_critical_when_over_budget(self) -> None:
        """CRITICAL when over budget."""
        budget = RequestBudget(total_ms=1)
        time.sleep(0.01)
        assert budget.degradation_level == DegradationLevel.CRITICAL

    def test_degradation_heavy_when_vector_skipped(self) -> None:
        """HEAVY when vector_search is skipped - Lines 79-80."""
        budget = RequestBudget(total_ms=500)
        budget.skip("vector_search")
        assert budget.degradation_level == DegradationLevel.HEAVY

    def test_degradation_heavy_when_embedding_skipped(self) -> None:
        """HEAVY when embedding is skipped - Lines 79-80."""
        budget = RequestBudget(total_ms=500)
        budget.skip("embedding")
        assert budget.degradation_level == DegradationLevel.HEAVY

    def test_degradation_light_when_tier5_skipped(self) -> None:
        """LIGHT when tier5_llm is skipped - Lines 81-82."""
        budget = RequestBudget(total_ms=500)
        budget.skip("tier5_llm")
        assert budget.degradation_level == DegradationLevel.LIGHT

    def test_degradation_light_when_tier4_skipped(self) -> None:
        """LIGHT when tier4_embedding is skipped - Lines 83-84."""
        budget = RequestBudget(total_ms=500)
        budget.skip("tier4_embedding")
        assert budget.degradation_level == DegradationLevel.LIGHT

    def test_degradation_moderate_for_other_skips(self) -> None:
        """MODERATE for other skipped operations - Line 85."""
        budget = RequestBudget(total_ms=500)
        budget.skip("some_other_operation")
        assert budget.degradation_level == DegradationLevel.MODERATE

    def test_degradation_priority_critical_over_heavy(self) -> None:
        """CRITICAL should take priority over other levels."""
        budget = RequestBudget(total_ms=1)
        budget.skip("vector_search")  # Would be HEAVY
        time.sleep(0.01)
        assert budget.degradation_level == DegradationLevel.CRITICAL

    def test_degradation_priority_heavy_over_light(self) -> None:
        """HEAVY should take priority over LIGHT."""
        budget = RequestBudget(total_ms=500)
        budget.skip("tier5_llm")  # Would be LIGHT
        budget.skip("vector_search")  # HEAVY
        assert budget.degradation_level == DegradationLevel.HEAVY


class TestIsDegraded:
    """Test is_degraded property."""

    def test_not_degraded_when_fresh(self) -> None:
        """is_degraded should be False when fresh."""
        budget = RequestBudget(total_ms=500)
        assert budget.is_degraded is False

    def test_degraded_when_operations_skipped(self) -> None:
        """is_degraded should be True when operations skipped."""
        budget = RequestBudget(total_ms=500)
        budget.skip("any_op")
        assert budget.is_degraded is True

    def test_degraded_when_over_budget(self) -> None:
        """is_degraded should be True when over budget."""
        budget = RequestBudget(total_ms=1)
        time.sleep(0.01)
        assert budget.is_degraded is True


class TestDegradationReasons:
    """Test degradation_reasons property."""

    def test_no_reasons_when_fresh(self) -> None:
        """No reasons when fresh and under budget."""
        budget = RequestBudget(total_ms=500)
        assert budget.degradation_reasons == []

    def test_reasons_for_skipped_operations(self) -> None:
        """Should list skipped operations with prefix."""
        budget = RequestBudget(total_ms=500)
        budget.skip("tier5_llm")
        budget.skip("vector_search")
        reasons = budget.degradation_reasons
        assert "budget_skip_tier5_llm" in reasons
        assert "budget_skip_vector_search" in reasons

    def test_reasons_include_overrun(self) -> None:
        """Should include budget_overrun when over budget."""
        budget = RequestBudget(total_ms=1)
        time.sleep(0.01)
        reasons = budget.degradation_reasons
        assert "budget_overrun" in reasons

    def test_reasons_combined(self) -> None:
        """Should combine skip and overrun reasons."""
        budget = RequestBudget(total_ms=1)
        budget.skip("tier5_llm")
        time.sleep(0.01)
        reasons = budget.degradation_reasons
        assert "budget_skip_tier5_llm" in reasons
        assert "budget_overrun" in reasons


class TestCostConstants:
    """Test cost constant values are sensible."""

    def test_cost_tier5_llm(self) -> None:
        """COST_TIER5_LLM should be reasonable."""
        budget = RequestBudget()
        assert budget.COST_TIER5_LLM == 150

    def test_cost_tier4_embedding(self) -> None:
        """COST_TIER4_EMBEDDING should be reasonable."""
        budget = RequestBudget()
        assert budget.COST_TIER4_EMBEDDING == 100

    def test_cost_vector_search(self) -> None:
        """COST_VECTOR_SEARCH should be reasonable."""
        budget = RequestBudget()
        assert budget.COST_VECTOR_SEARCH == 80

    def test_cost_hydration(self) -> None:
        """COST_HYDRATION should be reasonable."""
        budget = RequestBudget()
        assert budget.COST_HYDRATION == 50

    def test_cost_burst2(self) -> None:
        """COST_BURST2 should be reasonable."""
        budget = RequestBudget()
        assert budget.COST_BURST2 == 80
