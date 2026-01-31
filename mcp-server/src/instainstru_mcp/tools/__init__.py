"""Tool registration for InstaInstru MCP server."""

from . import (
    celery,
    founding,
    instructors,
    invites,
    metrics,
    observability,
    operations,
    search,
    sentry,
    sentry_debug,
    services,
)

__all__ = [
    "celery",
    "founding",
    "instructors",
    "invites",
    "metrics",
    "observability",
    "operations",
    "search",
    "sentry",
    "sentry_debug",
    "services",
]
