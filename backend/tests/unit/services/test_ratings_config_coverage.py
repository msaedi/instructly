"""Tests for app/services/ratings_config.py — coverage gap L21."""
from __future__ import annotations

import pytest

from app.services.ratings_config import DEFAULT_RATINGS_CONFIG, RatingsConfig


@pytest.mark.unit
class TestRatingsConfigCoverage:
    """Cover L21: prior_strength property."""

    def test_prior_strength_default(self) -> None:
        """L20-21: prior_strength returns sum of dirichlet_prior."""
        config = DEFAULT_RATINGS_CONFIG
        expected = sum(config.dirichlet_prior)
        assert config.prior_strength == expected
        assert config.prior_strength == 20.0

    def test_prior_strength_custom(self) -> None:
        config = RatingsConfig(dirichlet_prior=(1.0, 2.0, 3.0, 4.0, 5.0))
        assert config.prior_strength == 15.0

    def test_prior_strength_zeros(self) -> None:
        config = RatingsConfig(dirichlet_prior=(0.0, 0.0, 0.0, 0.0, 0.0))
        assert config.prior_strength == 0.0

    def test_default_values(self) -> None:
        """Verify default configuration values."""
        config = DEFAULT_RATINGS_CONFIG
        assert config.min_reviews_to_display == 3
        assert config.recency_half_life_months == 12
        assert config.duplicate_rater_secondary_weight == 0.2
        assert config.simple_shrinkage_prior_count == 30
        assert config.prior_mean_rating == 3.5

    def test_frozen_dataclass(self) -> None:
        """Config is frozen — no mutations allowed."""
        config = DEFAULT_RATINGS_CONFIG
        with pytest.raises(AttributeError):
            config.min_reviews_to_display = 5  # type: ignore[misc]
