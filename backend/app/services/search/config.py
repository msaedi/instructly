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

from app.core.config import settings


@dataclass
class SearchConfig:
    """Configuration for NL Search."""

    # Parsing model (for extracting constraints from queries)
    parsing_model: str = "gpt-5-nano"
    parsing_timeout_ms: int = 1000

    # Embedding model (for vector search)
    embedding_model: str = "text-embedding-3-small"
    embedding_timeout_ms: int = 2000

    # Location model (for Tier 5 location resolution)
    location_model: str = "gpt-4o-mini"

    # Location LLM timeout (for Tier 5 location resolution)
    location_timeout_ms: int = 3000

    # General settings
    max_retries: int = 2
    search_budget_ms: int = 500
    high_load_budget_ms: int = 300
    high_load_threshold: int = 10
    uncached_concurrency: int = 6

    @classmethod
    def from_env(cls) -> "SearchConfig":
        """Load configuration from environment variables."""
        return cls(
            parsing_model=os.getenv("OPENAI_PARSING_MODEL", "gpt-5-nano"),
            parsing_timeout_ms=int(os.getenv("OPENAI_PARSING_TIMEOUT_MS", "1000")),
            embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            embedding_timeout_ms=int(os.getenv("OPENAI_EMBEDDING_TIMEOUT_MS", "2000")),
            location_model=os.getenv("OPENAI_LOCATION_MODEL", settings.openai_location_model),
            location_timeout_ms=int(
                os.getenv(
                    "OPENAI_LOCATION_TIMEOUT_MS",
                    str(settings.openai_location_timeout_ms),
                )
            ),
            max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "2")),
            search_budget_ms=int(os.getenv("SEARCH_BUDGET_MS", "500")),
            high_load_budget_ms=int(os.getenv("SEARCH_HIGH_LOAD_BUDGET_MS", "300")),
            high_load_threshold=int(os.getenv("SEARCH_HIGH_LOAD_THRESHOLD", "10")),
            uncached_concurrency=int(os.getenv("UNCACHED_SEARCH_CONCURRENCY", "6")),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "parsing_model": self.parsing_model,
            "parsing_timeout_ms": self.parsing_timeout_ms,
            "embedding_model": self.embedding_model,
            "embedding_timeout_ms": self.embedding_timeout_ms,
            "location_model": self.location_model,
            "location_timeout_ms": self.location_timeout_ms,
            "max_retries": self.max_retries,
            "search_budget_ms": self.search_budget_ms,
            "high_load_budget_ms": self.high_load_budget_ms,
            "high_load_threshold": self.high_load_threshold,
            "uncached_concurrency": self.uncached_concurrency,
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
    location_model: Optional[str] = None,
    location_timeout_ms: Optional[int] = None,
    max_retries: Optional[int] = None,
    search_budget_ms: Optional[int] = None,
    high_load_budget_ms: Optional[int] = None,
    high_load_threshold: Optional[int] = None,
    uncached_concurrency: Optional[int] = None,
) -> SearchConfig:
    """
    Update search configuration at runtime.

    Used by admin panel for testing different settings.
    Changes are NOT persisted to environment - they reset on server restart.

    Args:
        parsing_model: New parsing model (e.g., "gpt-5-nano")
        parsing_timeout_ms: New parsing timeout in milliseconds
        embedding_model: New embedding model (e.g., "text-embedding-3-small")
        embedding_timeout_ms: New embedding timeout in milliseconds
        location_model: New location model (e.g., "gpt-4o-mini")
        location_timeout_ms: New location LLM timeout in milliseconds
        max_retries: OpenAI max retries for API calls
        search_budget_ms: Default request budget in milliseconds
        high_load_budget_ms: Budget used under high load
        high_load_threshold: Concurrent request threshold for high load
        uncached_concurrency: Max concurrent uncached searches per worker

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
        if location_model is not None:
            _config.location_model = location_model
            settings.openai_location_model = location_model
        if location_timeout_ms is not None:
            _config.location_timeout_ms = location_timeout_ms
            settings.openai_location_timeout_ms = location_timeout_ms
        if max_retries is not None:
            _config.max_retries = max_retries
        if search_budget_ms is not None:
            _config.search_budget_ms = search_budget_ms
        if high_load_budget_ms is not None:
            _config.high_load_budget_ms = high_load_budget_ms
        if high_load_threshold is not None:
            _config.high_load_threshold = high_load_threshold
        if uncached_concurrency is not None:
            _config.uncached_concurrency = uncached_concurrency

        return _config


def reset_search_config() -> SearchConfig:
    """
    Reset configuration to environment defaults.

    Used by admin panel to revert testing changes.
    """
    global _config
    with _config_lock:
        _config = SearchConfig.from_env()
        settings.openai_location_model = _config.location_model
        settings.openai_location_timeout_ms = _config.location_timeout_ms
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
