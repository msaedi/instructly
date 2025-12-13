# backend/app/services/search/config.py
"""
Configuration for NL Search OpenAI integration.

Provides runtime-configurable settings for:
- LLM parsing model and timeout
- Embedding model and timeout
- Max retries

Settings are loaded from environment variables at startup and can be
temporarily overridden via admin API for testing different models.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from threading import Lock
from typing import Any, Dict, List, Optional


@dataclass
class SearchConfig:
    """Configuration for NL Search."""

    # Parsing model (for extracting constraints from queries)
    parsing_model: str = "gpt-4o-mini"
    parsing_timeout_ms: int = 2000

    # Embedding model (for vector search)
    embedding_model: str = "text-embedding-3-small"
    embedding_timeout_ms: int = 2000

    # General settings
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> "SearchConfig":
        """Load configuration from environment variables."""
        return cls(
            parsing_model=os.getenv("OPENAI_PARSING_MODEL", "gpt-4o-mini"),
            parsing_timeout_ms=int(os.getenv("OPENAI_PARSING_TIMEOUT_MS", "2000")),
            embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            embedding_timeout_ms=int(os.getenv("OPENAI_EMBEDDING_TIMEOUT_MS", "2000")),
            max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "2")),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "parsing_model": self.parsing_model,
            "parsing_timeout_ms": self.parsing_timeout_ms,
            "embedding_model": self.embedding_model,
            "embedding_timeout_ms": self.embedding_timeout_ms,
            "max_retries": self.max_retries,
        }


# Thread-safe singleton pattern for config
_config: Optional[SearchConfig] = None
_config_lock = Lock()


def get_search_config() -> SearchConfig:
    """
    Get the search configuration singleton.

    Loads from environment on first access.
    """
    global _config
    if _config is None:
        with _config_lock:
            if _config is None:
                _config = SearchConfig.from_env()
    return _config


def update_search_config(
    parsing_model: Optional[str] = None,
    parsing_timeout_ms: Optional[int] = None,
    embedding_model: Optional[str] = None,
    embedding_timeout_ms: Optional[int] = None,
) -> SearchConfig:
    """
    Update search configuration at runtime.

    Used by admin panel for testing different settings.
    Changes are NOT persisted to environment - they reset on server restart.

    Args:
        parsing_model: New parsing model (e.g., "gpt-4o-mini")
        parsing_timeout_ms: New parsing timeout in milliseconds
        embedding_model: New embedding model (e.g., "text-embedding-3-small")
        embedding_timeout_ms: New embedding timeout in milliseconds

    Returns:
        Updated SearchConfig
    """
    global _config
    with _config_lock:
        if _config is None:
            _config = SearchConfig.from_env()

        if parsing_model is not None:
            _config.parsing_model = parsing_model
        if parsing_timeout_ms is not None:
            _config.parsing_timeout_ms = parsing_timeout_ms
        if embedding_model is not None:
            _config.embedding_model = embedding_model
        if embedding_timeout_ms is not None:
            _config.embedding_timeout_ms = embedding_timeout_ms

        return _config


def reset_search_config() -> SearchConfig:
    """
    Reset configuration to environment defaults.

    Used by admin panel to revert testing changes.
    """
    global _config
    with _config_lock:
        _config = SearchConfig.from_env()
        return _config


# Available models for UI dropdowns
AVAILABLE_PARSING_MODELS: List[Dict[str, str]] = [
    {
        "id": "gpt-5-nano",
        "name": "GPT-5 Nano",
        "description": "Fastest, cheapest ($0.05/1M input)",
    },
    {
        "id": "gpt-4o-mini",
        "name": "GPT-4o Mini",
        "description": "Fast and cost-effective ($0.15/1M input)",
    },
    {
        "id": "gpt-4o-mini-2024-07-18",
        "name": "GPT-4o Mini (Pinned)",
        "description": "Pinned version for consistency",
    },
    {
        "id": "gpt-4o",
        "name": "GPT-4o",
        "description": "Most capable, higher cost ($5/1M input)",
    },
]

AVAILABLE_EMBEDDING_MODELS: List[Dict[str, str]] = [
    {
        "id": "text-embedding-3-small",
        "name": "text-embedding-3-small",
        "description": "Recommended balance of quality and cost ($0.02/1M)",
    },
    {
        "id": "text-embedding-3-large",
        "name": "text-embedding-3-large",
        "description": "Higher quality, higher cost ($0.13/1M)",
    },
]
