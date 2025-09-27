from datetime import datetime, timedelta, timezone

import pytest

from app.services.ratings_config import RatingsConfig
from app.services.ratings_math import (
    compute_dirichlet_rating,
    compute_simple_shrinkage,
    confidence_label,
    dirichlet_prior_mean,
    display_policy,
)


class _Review:
    def __init__(self, rating: int, days_ago: int = 0, student_id: str = "s1"):
        self.rating = rating
        self.created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
        self.student_id = student_id


def test_simple_shrinkage_basic():
    cfg = RatingsConfig(simple_shrinkage_prior_count=30, prior_mean_rating=3.5)
    # with no data, returns prior mean
    assert compute_simple_shrinkage(0, 0, cfg) == pytest.approx(3.5)
    # with some data, moves toward sample mean
    # sample mean 5.0 over 10 reviews -> (30*3.5 + 50) / 40 = 3.875
    assert compute_simple_shrinkage(50, 10, cfg) == pytest.approx(3.875)


def test_dirichlet_prior_mean():
    cfg = RatingsConfig(dirichlet_prior=(0.5, 0.5, 1.0, 4.0, 14.0))
    pm = dirichlet_prior_mean(cfg)
    # sanity: mean is in [1,5] and > 4.0
    assert 4.0 < pm < 5.0


def test_compute_dirichlet_rating_recency_weighting():
    cfg = RatingsConfig(recency_half_life_months=12)
    # Two 5-star reviews: one fresh, one a year old; fresh should carry more weight
    reviews = [_Review(5, days_ago=0), _Review(5, days_ago=365)]
    result = compute_dirichlet_rating(reviews, config=cfg)
    assert 0 <= result["total_reviews"] <= 2
    assert 4.0 < result["rating"] <= 5.0


def test_compute_dirichlet_rating_duplicate_dampening():
    cfg = RatingsConfig(duplicate_rater_secondary_weight=0.2)
    # Same student leaves two 5-star reviews on different bookings
    reviews = [_Review(5, days_ago=0, student_id="s1"), _Review(5, days_ago=1, student_id="s1")]
    result = compute_dirichlet_rating(reviews, config=cfg)
    # Effective count should be < raw count due to dampening
    assert result["total_reviews_effective"] < result["total_reviews"]


def test_display_policy_thresholds():
    cfg = RatingsConfig(min_reviews_to_display=3)
    assert display_policy(4.7, 0, cfg) is None
    assert display_policy(4.7, 2, cfg) is None
    assert display_policy(4.7, 3, cfg) is not None
    # for low counts >= 3, includes (New)
    assert "New" in display_policy(4.7, 3, cfg)
    # for higher counts, no (New)
    assert "New" not in display_policy(4.7, 10, cfg)


def test_confidence_label():
    assert confidence_label(0) == "new"
    assert confidence_label(10) == "establishing"
    assert confidence_label(50) == "established"
    assert confidence_label(1000) == "trusted"
