"""Shared public types for the message repository facade."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class AtomicMarkResult:
    """Result of an atomic mark-read operation."""

    rowcount: int
    message_ids: List[str]
    timestamp: Optional[datetime]
