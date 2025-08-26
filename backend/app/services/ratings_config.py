from dataclasses import dataclass
from typing import Final, Tuple


@dataclass(frozen=True)
class RatingsConfig:
    # Display/UI policy
    min_reviews_to_display: int = 3

    # Dirichlet prior over 1..5-star histogram (virtual reviews)
    dirichlet_prior: Tuple[float, ...] = (0.5, 0.5, 1.0, 4.0, 14.0)
    recency_half_life_months: int = 12
    duplicate_rater_secondary_weight: float = 0.2

    # Simple shrinkage (legacy per-service breakdown) and defensive fallback
    simple_shrinkage_prior_count: int = 30
    prior_mean_rating: float = 3.5

    @property
    def prior_strength(self) -> float:
        return float(sum(self.dirichlet_prior))


DEFAULT_RATINGS_CONFIG: Final = RatingsConfig()
