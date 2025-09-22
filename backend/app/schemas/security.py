from typing import List, Optional

from pydantic import BaseModel, Field

from ._strict_base import StrictRequestModel


class PasswordChangeRequest(StrictRequestModel):
    current_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=8)


class PasswordChangeResponse(BaseModel):
    message: str


class LoginResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: Optional[str] = None
    requires_2fa: bool = False
    temp_token: Optional[str] = None


class TFASetupInitiateResponse(BaseModel):
    secret: str
    qr_code_data_url: str
    otpauth_url: str


class TFASetupVerifyRequest(StrictRequestModel):
    code: str


class TFASetupVerifyResponse(BaseModel):
    enabled: bool
    backup_codes: List[str]


class TFADisableRequest(StrictRequestModel):
    current_password: str


class TFADisableResponse(BaseModel):
    message: str


class TFAStatusResponse(BaseModel):
    enabled: bool
    verified_at: Optional[str] = None
    last_used_at: Optional[str] = None


class TFAVerifyLoginRequest(StrictRequestModel):
    temp_token: str
    code: Optional[str] = None
    backup_code: Optional[str] = None


class TFAVerifyLoginResponse(BaseModel):
    access_token: str
    token_type: str


class BackupCodesResponse(BaseModel):
    backup_codes: List[str]
