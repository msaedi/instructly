from typing import Any, Dict, List, Optional

from pydantic import ConfigDict, Field

from ._strict_base import StrictModel


class CoverageFeatureCollectionResponse(StrictModel):
    type: str
    features: List[Dict[str, Any]]

    # Maintain strict extras while satisfying contract tests.
    model_config = StrictModel.model_config


class NYCZipCheckResponse(StrictModel):
    """Response payload for lightweight NYC ZIP verification."""

    is_nyc: bool
    borough: Optional[str] = None


class AddressDeleteResponse(StrictModel):
    """Standard delete acknowledgement for address resources."""

    model_config = ConfigDict(title="AddressDeleteResponse")

    success: bool
    message: str


class SelectorSearchTerm(StrictModel):
    """A searchable alias for a display item."""

    term: str
    type: str


class SelectorDisplayItem(StrictModel):
    """A single selectable neighborhood entry."""

    display_name: str
    display_key: str
    borough: str
    nta_ids: List[str]
    display_order: int
    search_terms: List[SelectorSearchTerm]
    additional_boroughs: List[str] = Field(default_factory=list)


class SelectorBorough(StrictModel):
    """A borough group."""

    borough: str
    items: List[SelectorDisplayItem]
    item_count: int


class NeighborhoodSelectorResponse(StrictModel):
    """Complete selector data for a market."""

    market: str
    boroughs: List[SelectorBorough]
    total_items: int


__all__ = [
    "AddressDeleteResponse",
    "CoverageFeatureCollectionResponse",
    "NeighborhoodSelectorResponse",
    "NYCZipCheckResponse",
    "SelectorBorough",
    "SelectorDisplayItem",
    "SelectorSearchTerm",
]
