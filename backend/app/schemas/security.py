from pydantic import BaseModel, Field


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=8)


class PasswordChangeResponse(BaseModel):
    message: str
