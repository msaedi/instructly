"""Authentication helpers for MCP server requests."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional, TYPE_CHECKING

import jwt
from jwt import PyJWKClient, PyJWKClientError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .config import Settings


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
def _get_auth0_validator(
    domain: str | None, audience: str | None
) -> Optional[Auth0TokenValidator]:
    if bool(domain) != bool(audience):
        logger.warning(
            "Partial Auth0 config detected: both INSTAINSTRU_MCP_AUTH0_DOMAIN and "
            "INSTAINSTRU_MCP_AUTH0_AUDIENCE must be set. Auth0 validation disabled."
        )
        return None

    if not domain or not audience:
        logger.info(
            "Auth0 not configured (INSTAINSTRU_MCP_AUTH0_DOMAIN or "
            "INSTAINSTRU_MCP_AUTH0_AUDIENCE missing)"
        )
        return None

    logger.info("Auth0 configured for domain: %s, audience: %s", domain, audience)
    return Auth0TokenValidator(domain=domain, audience=audience)


def get_auth0_validator(
    *, settings: Optional["Settings"] = None
) -> Optional[Auth0TokenValidator]:
    """Return Auth0 validator singleton, or None if not configured."""
    if settings is None:
        from .config import Settings

        token = os.environ.get("INSTAINSTRU_MCP_API_SERVICE_TOKEN", "")
        settings = Settings(api_service_token=token)

    return _get_auth0_validator(settings.auth0_domain, settings.auth0_audience)


get_auth0_validator.cache_clear = _get_auth0_validator.cache_clear  # type: ignore[attr-defined]
