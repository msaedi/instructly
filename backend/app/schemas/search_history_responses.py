from ._strict_base import StrictModel

"""Response models for search history endpoints."""

from pydantic import ConfigDict


class SearchInteractionResponse(StrictModel):
    """Response for recording search interaction."""

    success: bool
    message: str = "Interaction recorded successfully"
    status: str = "tracked"
    interaction_id: str

    # Harden response DTO to reject accidental extras in construction paths
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
