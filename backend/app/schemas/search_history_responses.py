"""Response models for search history endpoints."""

from pydantic import BaseModel


class SearchInteractionResponse(BaseModel):  # type: ignore[misc]
    """Response for recording search interaction."""

    success: bool
    message: str = "Interaction recorded successfully"
    status: str = "tracked"
    interaction_id: str
