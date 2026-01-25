"""Authentication helpers for MCP server requests."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

import jwt
from jwt import PyJWKClient, PyJWKClientError

from .config import Settings

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when MCP server auth configuration is invalid."""


class MCPAuth:
    """Builds backend auth headers using a single service token."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get_headers(self, request_id: str) -> dict:
        token = self.settings.api_service_token.strip()
        if not token:
            raise AuthenticationError("api_service_token_missing")
        return {
            "Authorization": f"Bearer {token}",
            "X-Request-Id": request_id,
        }


class Auth0TokenValidator:
    """Validates Auth0 JWT tokens."""

    def __init__(self, domain: str, audience: str) -> None:
        self.domain = domain
        self.audience = audience
        self.issuer = f"https://{domain}/"
        self.jwks_url = f"https://{domain}/.well-known/jwks.json"
        self._jwks_client: Optional[PyJWKClient] = None

    @property
    def jwks_client(self) -> PyJWKClient:
        """Lazy-load JWKS client."""
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(
                self.jwks_url,
                cache_keys=True,
                lifespan=3600,
            )
        return self._jwks_client

    def validate(self, token: str) -> dict:
        """Validate an Auth0 JWT token and return decoded claims."""
        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer,
                options={
                    "require": ["exp", "iat", "sub"],
                    "verify_exp": True,
                    "verify_iat": True,
                },
            )
            logger.debug(
                "Auth0 token validated for subject: %s",
                claims.get("sub"),
            )
            return claims
        except PyJWKClientError as exc:
            logger.warning("JWKS client error: %s", exc)
            raise jwt.InvalidTokenError(
                f"Could not fetch signing key: {exc}"
            ) from exc
        except jwt.ExpiredSignatureError:
            logger.warning("Auth0 token expired")
            raise
        except jwt.InvalidAudienceError:
            logger.warning("Invalid audience in token, expected: %s", self.audience)
            raise
        except jwt.InvalidIssuerError:
            logger.warning("Invalid issuer in token, expected: %s", self.issuer)
            raise
        except jwt.InvalidTokenError as exc:
            logger.warning("Invalid Auth0 token: %s", exc)
            raise


@lru_cache(maxsize=1)
def get_auth0_validator() -> Optional[Auth0TokenValidator]:
    """Return Auth0 validator singleton, or None if not configured."""
    domain = os.environ.get("AUTH0_DOMAIN")
    audience = os.environ.get("AUTH0_AUDIENCE")

    if not domain or not audience:
        logger.info("Auth0 not configured (AUTH0_DOMAIN or AUTH0_AUDIENCE missing)")
        return None

    logger.info("Auth0 configured for domain: %s, audience: %s", domain, audience)
    return Auth0TokenValidator(domain=domain, audience=audience)
