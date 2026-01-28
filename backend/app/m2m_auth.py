"""Machine-to-machine authentication using WorkOS OAuth2 Client Credentials."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from typing import Optional

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
from pydantic import BaseModel

from app.core.config import settings


class M2MTokenClaims(BaseModel):
    """Claims from a verified M2M JWT."""

    sub: str
    iss: str
    aud: str
    exp: int
    iat: int
    scope: str


class JWKSCache:
    """Cache for WorkOS JWKS with 1-hour TTL."""

    def __init__(self) -> None:
        self._keys: Optional[dict[str, dict[str, object]]] = None
        self._fetched_at: Optional[datetime] = None
        self._ttl = timedelta(hours=1)
        self._lock = asyncio.Lock()

    async def get_signing_key(self, token: str) -> dict[str, object]:
        """Get the signing key for a token, fetching JWKS if needed."""
        if not settings.workos_jwks_url:
            raise ValueError("WorkOS JWKS URL not configured")

        # Get kid from token header before fetching
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            raise ValueError("Missing kid in token header")

        if self._should_refresh():
            await self._fetch_jwks()

        if not self._keys or kid not in self._keys:
            await self._fetch_jwks()
            if not self._keys or kid not in self._keys:
                raise ValueError(f"Unknown signing key: {kid}")

        return self._keys[kid]

    def _should_refresh(self) -> bool:
        if self._keys is None or self._fetched_at is None:
            return True
        return datetime.now(timezone.utc) - self._fetched_at > self._ttl

    async def _fetch_jwks(self) -> None:
        """Fetch JWKS from WorkOS."""
        async with self._lock:
            if not self._should_refresh() and self._keys:
                return
            if not settings.workos_jwks_url:
                raise ValueError("WorkOS JWKS URL not configured")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(settings.workos_jwks_url)
                response.raise_for_status()
                jwks = response.json()

            self._keys = {key["kid"]: key for key in jwks.get("keys", []) if "kid" in key}
            self._fetched_at = datetime.now(timezone.utc)


_jwks_cache = JWKSCache()


async def verify_m2m_token(token: str) -> Optional[M2MTokenClaims]:
    """Verify a WorkOS M2M JWT token."""
    if not token:
        return None
    if (
        not settings.workos_jwks_url
        or not settings.workos_m2m_audience
        or not settings.workos_issuer
    ):
        return None

    try:
        signing_key = await _jwks_cache.get_signing_key(token)
        public_key = RSAAlgorithm.from_jwk(json.dumps(signing_key))
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.workos_m2m_audience,
            issuer=settings.workos_issuer,
        )
        return M2MTokenClaims(**payload)
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None


def has_scope(claims: M2MTokenClaims, required_scope: str) -> bool:
    """Check if token has required scope."""
    scopes = claims.scope.split() if claims.scope else []
    return required_scope in scopes
