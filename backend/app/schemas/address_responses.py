from typing import Any, Dict, List, Optional

from ._strict_base import StrictModel


class CoverageFeatureCollectionResponse(StrictModel):
    type: str
    features: List[Dict[str, Any]]

    # Maintain strict extras while satisfying legacy contract tests.
    model_config = StrictModel.model_config


class NYCZipCheckResponse(StrictModel):
    """Response payload for lightweight NYC ZIP verification."""

    is_nyc: bool
    borough: Optional[str] = None


class DeleteResponse(StrictModel):
    """Standard delete acknowledgement for address resources."""

    success: bool
    message: str


class NeighborhoodItem(StrictModel):
    """Single neighborhood entry with optional borough metadata."""

    id: str
    name: str
    borough: Optional[str] = None
    code: Optional[str] = None


class NeighborhoodsListResponse(StrictModel):
    """Paginated list of neighborhoods."""

    items: List[NeighborhoodItem]
    total: int
    page: Optional[int] = None
    per_page: Optional[int] = None


__all__ = [
    "CoverageFeatureCollectionResponse",
    "DeleteResponse",
    "NeighborhoodItem",
    "NeighborhoodsListResponse",
    "NYCZipCheckResponse",
]
