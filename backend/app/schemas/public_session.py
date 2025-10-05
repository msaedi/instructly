from pydantic import ConfigDict

from ._strict_base import StrictModel


class GuestSessionResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    guest_id: str
