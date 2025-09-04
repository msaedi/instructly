"""Rate limiting engine (GCRA) with Redis backend.

Shadow-mode foundation: no endpoints wired yet.
"""

from .dependency import rate_limit
from .gcra import Decision, gcra_decide

__all__ = [
    "Decision",
    "gcra_decide",
    "rate_limit",
]
