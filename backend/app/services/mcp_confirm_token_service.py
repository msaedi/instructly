"""Confirm token service for MCP write operations."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from typing import Any, cast

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import MCPTokenError, ServiceException
from app.services.base import BaseService


def _secret_value(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "get_secret_value"):
        return value.get_secret_value() or ""
    return str(value)


class MCPConfirmTokenService(BaseService):
    """
    Generates confirm tokens for MCP write operations.

    Tokens are signed, expire in 30 minutes, and encode the operation payload hash.
    """

    TOKEN_EXPIRY_MINUTES = 30

    def __init__(self, db: Session):
        super().__init__(db)
        self._secret = self._resolve_secret().encode("utf-8")

    @BaseService.measure_operation("mcp_confirm_token.generate")
    def generate_token(self, payload: dict[str, Any], actor_id: str) -> tuple[str, datetime]:
        """
        Generate a confirm token for a payload.
        Returns (token, expires_at).
        Token format: base64(json({payload_hash, actor_id, expires_at, signature}))
        """
        payload_hash = self._hash_payload(payload)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.TOKEN_EXPIRY_MINUTES)
        signature = self._sign(payload_hash, actor_id, expires_at)
        token_payload = {
            "payload_hash": payload_hash,
            "actor_id": actor_id,
            "expires_at": expires_at.isoformat(),
            "signature": signature,
            "payload": payload,
        }
        encoded = self._b64encode(token_payload)
        return encoded, expires_at

    @BaseService.measure_operation("mcp_confirm_token.validate")
    def validate_token(self, token: str, expected_payload: dict[str, Any], actor_id: str) -> bool:
        """
        Validate token matches payload and hasn't expired.
        Raises MCPTokenError on failure with specific reason.
        """
        token_data = self._decode_token(token)
        payload_hash = token_data.get("payload_hash")
        token_actor_id = token_data.get("actor_id")
        expires_raw = token_data.get("expires_at")
        signature = token_data.get("signature")

        if not payload_hash or not token_actor_id or not expires_raw or not signature:
            raise MCPTokenError("invalid_format")

        expected_hash = self._hash_payload(expected_payload)
        if not secrets.compare_digest(expected_hash, str(payload_hash)):
            raise MCPTokenError("payload_mismatch")

        if str(token_actor_id) != actor_id:
            raise MCPTokenError("actor_mismatch")

        expires_at = self._parse_expires(expires_raw)
        if datetime.now(timezone.utc) > expires_at:
            raise MCPTokenError("expired")

        expected_signature = self._sign(expected_hash, actor_id, expires_at)
        if not secrets.compare_digest(expected_signature, str(signature)):
            raise MCPTokenError("invalid_signature")

        return True

    @BaseService.measure_operation("mcp_confirm_token.decode")
    def decode_token(self, token: str) -> dict[str, Any]:
        """Decode token payload for downstream use."""
        return self._decode_token(token)

    def _resolve_secret(self) -> str:
        secret = _secret_value(getattr(settings, "mcp_token_secret", None))
        if not secret:
            secret = _secret_value(getattr(settings, "secret_key", None))
        if not secret:
            raise ServiceException(
                "MCP token secret not configured", code="mcp_token_secret_missing"
            )
        return secret

    def _hash_payload(self, payload: dict[str, Any]) -> str:
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    def _sign(self, payload_hash: str, actor_id: str, expires_at: datetime) -> str:
        message = f"{payload_hash}|{actor_id}|{expires_at.isoformat()}".encode("utf-8")
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def _parse_expires(self, raw: str) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(raw))
        except ValueError as exc:
            raise MCPTokenError("invalid_format") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _decode_token(self, token: str) -> dict[str, Any]:
        raw_token = token[5:] if token.startswith("ctok_") else token
        try:
            decoded = self._b64decode(raw_token)
        except Exception as exc:
            raise MCPTokenError("invalid_format") from exc
        if not isinstance(decoded, dict):
            raise MCPTokenError("invalid_format")
        return decoded

    @staticmethod
    def _b64encode(payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
            "utf-8"
        )
        token = base64.urlsafe_b64encode(raw).decode("utf-8")
        return token.rstrip("=")

    @staticmethod
    def _b64decode(token: str) -> dict[str, Any]:
        padding = "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode((token + padding).encode("utf-8"))
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise ValueError("Invalid token payload")
        return cast(dict[str, Any], decoded)
