# backend/app/utils/url_validation.py
"""
URL and origin validation utilities.

Shared utility for validating allowed origins for Stripe Connect return URLs
and other security-sensitive URL handling.
"""

from urllib.parse import urlparse

# Explicit list of allowed local development IPs
# Only these specific IPs are allowed, not any arbitrary IP address
ALLOWED_LOCAL_IPS: frozenset[str] = frozenset(
    {
        "127.0.0.1",
        "localhost",
    }
)


def is_allowed_origin(candidate: str | None) -> bool:
    """
    Check if a candidate origin is allowed for security-sensitive URLs.

    Used for validating Stripe Connect return URLs and similar cases where
    we need to ensure the URL is from a trusted origin.

    Args:
        candidate: The origin URL to validate (e.g., "https://beta.instainstru.com")

    Returns:
        True if the origin is allowed, False otherwise

    Security Note:
        Only allows explicit local IPs (127.0.0.1, localhost), not arbitrary IP addresses.
        This prevents open redirect vulnerabilities.
    """
    if not candidate:
        return False

    try:
        parsed = urlparse(candidate)
        host = (parsed.hostname or "").lower()
        scheme = (parsed.scheme or "").lower()

        # Allow explicit local development hosts
        if host in ALLOWED_LOCAL_IPS:
            return True

        # Allow beta-local development domain
        if host == "beta-local.instainstru.com":
            return True

        # For non-local hosts, require HTTPS
        if scheme != "https":
            return False

        # Allow production domains
        if host in {"instainstru.com", "www.instainstru.com"}:
            return True

        # Allow subdomains of instainstru.com
        if host.endswith(".instainstru.com"):
            return True

        return False
    except Exception:
        return False


def origin_from_header(value: str | None) -> str | None:
    """
    Extract a normalized origin from an HTTP header value.

    Args:
        value: The raw header value (Origin or Referer header)

    Returns:
        Normalized origin string (scheme://host:port) or None if invalid
    """
    if not value:
        return None

    try:
        parsed = urlparse(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    except Exception:
        return None

    return None
