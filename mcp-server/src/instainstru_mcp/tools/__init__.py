"""Tool registration for InstaInstru MCP server."""

from . import (
    celery,
    command_center,
    deploy,
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
    "command_center",
    "deploy",
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
