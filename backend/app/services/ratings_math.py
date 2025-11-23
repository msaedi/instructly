from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from .ratings_config import DEFAULT_RATINGS_CONFIG, RatingsConfig


def compute_simple_shrinkage(
    rating_sum: float, count: int, config: RatingsConfig = DEFAULT_RATINGS_CONFIG
) -> float:
    c = float(config.simple_shrinkage_prior_count)
    m = float(config.prior_mean_rating)
    if count <= 0:
        return m
    return (c * m + float(rating_sum)) / (c + float(count))


def dirichlet_prior_mean(config: RatingsConfig = DEFAULT_RATINGS_CONFIG) -> float:
    v = config.dirichlet_prior
    c = float(sum(v))
    if c <= 0:
        return float(config.prior_mean_rating)
    return sum((i + 1) * float(v[i]) for i in range(5)) / c


def compute_dirichlet_rating(
    reviews: Iterable[Any],
    *,
    created_at_attr: str = "created_at",
    rating_attr: str = "rating",
    student_attr: str = "student_id",
    config: RatingsConfig = DEFAULT_RATINGS_CONFIG,
) -> dict[str, float | int | None]:
    reviews = list(reviews)
    if not reviews:
        pm = dirichlet_prior_mean(config)
        return {
            "rating": round(pm, 1),
            "total_reviews": 0,
            "total_reviews_effective": 0,
            "display_rating": None,
        }

    weights = [0.0, 0.0, 0.0, 0.0, 0.0]
    total_effective = 0.0
    now = datetime.now(timezone.utc)
    half_life_days = config.recency_half_life_months * 30

    for r in reviews:
        t = getattr(r, created_at_attr) or now
        if getattr(t, "tzinfo", None) is None:
            t = t.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - t).total_seconds() / 86400.0)
        w = 0.5 ** (age_days / half_life_days) if half_life_days > 0 else 1.0

        # Duplicate rater dampening for subsequent reviews by same student
        try:
            sid = getattr(r, student_attr)
            count_before = sum(
                1
                for rv in reviews
                if getattr(rv, student_attr) == sid
                and getattr(rv, created_at_attr) <= getattr(r, created_at_attr)
            )
            if count_before > 1:
                w *= config.duplicate_rater_secondary_weight
        except Exception:
            pass

        k = max(1, min(5, int(getattr(r, rating_attr))))
        weights[k - 1] += w
        total_effective += w

    v = config.dirichlet_prior
    num = sum((i + 1) * (weights[i] + float(v[i])) for i in range(5))
    den = sum(weights[i] + float(v[i]) for i in range(5))
    posterior_mean = num / den if den > 0 else float(config.prior_mean_rating)
    rating = round(posterior_mean, 1)
    count_effective = int(round(total_effective))
    raw_count = len(reviews)
    return {
        "rating": rating,
        "total_reviews": raw_count,
        "total_reviews_effective": count_effective,
    }


def display_policy(
    rating: float, count: int, config: RatingsConfig = DEFAULT_RATINGS_CONFIG
) -> Optional[str]:
    if count < config.min_reviews_to_display:
        return None
    precision = 2 if count < 10 else 1
    formatted = f"{rating:.{precision}f}"
    if count < 5:
        return f"{formatted}★ (New)"
    return f"{formatted}★"


def confidence_label(count: int) -> str:
    if count < 5:
        return "new"
    if count < 25:
        return "establishing"
    if count < 100:
        return "established"
    return "trusted"
