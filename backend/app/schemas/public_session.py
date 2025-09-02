from pydantic import BaseModel


class GuestSessionResponse(BaseModel):
    guest_id: str
