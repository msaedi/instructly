"""Minimal Checkr API client for instructor background checks."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, cast
from uuid import uuid4

import httpx
from pydantic import SecretStr

logger = logging.getLogger(__name__)


class CheckrError(RuntimeError):
    """Raised when the Checkr API responds with an error."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        *,
        error_type: str | None = None,
        error_body: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type
        self.error_body = error_body


class CheckrClient:
    """Thin client for the Checkr REST API."""

    def __init__(
        self,
        *,
        api_key: str | SecretStr,
        base_url: str = "https://api.checkr.com/v1",
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        secret_value = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        if not secret_value:
            raise ValueError("Checkr API key must be provided")

        self._api_key = secret_value
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport
        # Checkr uses HTTP Basic auth where the API key is the username and the password is blank.
        # Keeping a BasicAuth instance ensures every request carries the correct Authorization header.
        self._auth = httpx.BasicAuth(self._api_key, "")

    def create_candidate(
        self,
        *,
        idempotency_key: str | None = None,
        **payload: Any,
    ) -> Dict[str, Any]:
        """Create a new candidate in Checkr."""

        body: Dict[str, Any] = {key: value for key, value in payload.items() if value is not None}
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self.request("POST", "/candidates", json_body=body, headers=headers)

    def create_invitation(self, **payload: Any) -> Dict[str, Any]:
        """Create a hosted invitation for a candidate."""

        body: Dict[str, Any] = {key: value for key, value in payload.items() if value is not None}
        return self.request("POST", "/invitations", json_body=body)

    def get_report(self, report_id: str) -> Dict[str, Any]:
        """Fetch a Checkr report by identifier."""

        if not report_id:
            raise ValueError("report_id must be provided")
        return self.request("GET", f"/reports/{report_id}")

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Dict[str, Any] | None = None,
        params: Dict[str, Any] | None = None,
        headers: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        """Perform a raw Checkr API request and return the parsed JSON payload."""

        url = f"{self._base_url}{path}"
        with httpx.Client(
            timeout=self._timeout,
            transport=self._transport,
            auth=self._auth,
            headers={"Accept": "application/json"},
        ) as client:
            request = client.build_request(
                method,
                url,
                json=json_body,
                params=params,
                headers=headers,
            )
            if logger.isEnabledFor(logging.DEBUG):
                auth_header = request.headers.get("Authorization", "") or ""
                auth_scheme = auth_header.split(" ")[0] if auth_header else "missing"
                logger.debug(
                    "CheckrClient request",
                    extra={
                        "evt": "checkr_request",
                        "method": request.method,
                        "path": path,
                        "auth_scheme": auth_scheme,
                    },
                )
            try:
                response = client.send(request)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                error_payload: Any | None = None
                error_type: str | None = None
                try:
                    error_payload = exc.response.json()
                    if isinstance(error_payload, dict):
                        error_type = (
                            error_payload.get("error")
                            or error_payload.get("name")
                            or error_payload.get("type")
                        )
                except json.JSONDecodeError:
                    error_payload = exc.response.text

                logger.error(
                    "Checkr API error %s for %s %s: %s",
                    status,
                    method,
                    path,
                    exc.response.text[:500],
                )
                raise CheckrError(
                    message=f"Checkr API responded with status {status}",
                    status_code=status,
                    error_type=error_type,
                    error_body=error_payload,
                ) from exc
            except httpx.RequestError as exc:
                logger.error("Checkr request failure for %s %s: %s", method, path, str(exc))
                raise CheckrError("Failed to reach Checkr API") from exc

        try:
            return cast(Dict[str, Any], response.json())
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON from Checkr for %s %s: %s", method, path, response.text)
            raise CheckrError("Received malformed JSON from Checkr") from exc


class FakeCheckrClient(CheckrClient):
    """Simple in-memory stub that mimics Checkr for non-production flows."""

    def __init__(self) -> None:
        super().__init__(api_key="fake-checkr-key", base_url="https://api.checkr.com/v1")
        self._logger = logging.getLogger(self.__class__.__name__)

    def create_candidate(
        self,
        *,
        idempotency_key: str | None = None,
        **payload: Any,
    ) -> Dict[str, Any]:
        candidate_id = f"fake-candidate-{uuid4().hex}"
        self._logger.debug("Fake candidate created", extra={"candidate_id": candidate_id})
        return {
            "id": candidate_id,
            "object": "candidate",
            **{k: v for k, v in payload.items() if v is not None},
        }

    def create_invitation(self, **payload: Any) -> Dict[str, Any]:
        candidate_id = payload.get("candidate_id") or f"fake-candidate-{uuid4().hex}"
        package = payload.get("package", "basic_plus")
        report_id = f"rpt_fake_{uuid4().hex}"
        invitation_id = f"inv_fake_{uuid4().hex}"
        self._logger.debug(
            "Fake invitation created",
            extra={"candidate_id": candidate_id, "package": package, "report_id": report_id},
        )
        return {
            "id": invitation_id,
            "object": "invitation",
            "candidate_id": candidate_id,
            "package": package,
            "report_id": report_id,
            **{k: v for k, v in payload.items() if v is not None},
        }

    def get_report(self, report_id: str) -> Dict[str, Any]:
        resolved_id = report_id or f"rpt_fake_{uuid4().hex}"
        return {
            "id": resolved_id,
            "object": "report",
            "result": "clear",
            "status": "complete",
        }
