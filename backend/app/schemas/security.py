from typing import List, Optional

from pydantic import ConfigDict, Field

from ._strict_base import StrictModel, StrictRequestModel


class PasswordChangeRequest(StrictRequestModel):
    current_password: str = Field(..., min_length=6)
    new_password: str = Field(..., min_length=8)


class PasswordChangeResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    message: str


class LoginResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    requires_2fa: bool = False
    temp_token: Optional[str] = None


class TFASetupInitiateResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    secret: str
    qr_code_data_url: str
    otpauth_url: str


class TFASetupVerifyRequest(StrictRequestModel):
    code: str


class TFASetupVerifyResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    enabled: bool
    backup_codes: List[str]


class TFADisableRequest(StrictRequestModel):
    current_password: str


class TFADisableResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    message: str


class TFAStatusResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    enabled: bool
    verified_at: Optional[str] = None
    last_used_at: Optional[str] = None


class TFAVerifyLoginRequest(StrictRequestModel):
    temp_token: str
    code: Optional[str] = None
    backup_code: Optional[str] = None


class TFAVerifyLoginResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class BackupCodesResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    backup_codes: List[str]


class SessionInvalidationResponse(StrictModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    message: str
