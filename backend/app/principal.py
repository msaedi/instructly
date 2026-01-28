"""Principal abstractions for authenticated MCP callers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@runtime_checkable
class Principal(Protocol):
    """Represents the authenticated entity making a request."""

    @property
    def id(self) -> str:
        """Unique identifier for audit trails."""
        ...

    @property
    def identifier(self) -> str:
        """Human-readable identifier (email for users, client_id for services)."""
        ...

    @property
    def principal_type(self) -> Literal["user", "service"]:
        """Type of principal."""
        ...


@dataclass(frozen=True)
class UserPrincipal:
    """Principal backed by a database User."""

    user_id: str
    email: str

    @property
    def id(self) -> str:
        return self.user_id

    @property
    def identifier(self) -> str:
        return self.email

    @property
    def principal_type(self) -> Literal["user", "service"]:
        return "user"


@dataclass(frozen=True)
class ServicePrincipal:
    """Principal backed by M2M token claims."""

    client_id: str
    org_id: str
    scopes: tuple[str, ...]

    @property
    def id(self) -> str:
        return self.client_id

    @property
    def identifier(self) -> str:
        return self.client_id

    @property
    def principal_type(self) -> Literal["user", "service"]:
        return "service"

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes
