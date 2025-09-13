"""Response models for search history endpoints."""

from .base import StrictModel


class SearchInteractionResponse(StrictModel):
    """Response for recording search interaction."""

    success: bool
    message: str = "Interaction recorded successfully"
    status: str = "tracked"
    interaction_id: str
