from __future__ import annotations

from pydantic import Field, SecretStr


class SearchSettingsMixin:
    guest_session_expiry_days: int = 30
    soft_delete_retention_days: int = 90
    guest_session_purge_days: int = 90
    search_history_max_per_user: int = 1000
    search_analytics_enabled: bool = True
    openai_location_model: str = Field(
        default="gpt-4o-mini",
        alias="OPENAI_LOCATION_MODEL",
        description="Model used for Tier 5 location resolution",
    )
    openai_location_timeout_ms: int = Field(
        default=3000,
        alias="OPENAI_LOCATION_TIMEOUT_MS",
        ge=500,
        description="Timeout (ms) for Tier 5 location resolution",
    )
    openai_call_concurrency: int = Field(
        default=3,
        alias="OPENAI_CALL_CONCURRENCY",
        ge=1,
        description=(
            "Maximum concurrent OpenAI API calls per worker.\n\n"
            "Tuning guidelines:\n"
            "- Free tier: 3 (default)\n"
            "- Tier 1 ($5/mo): 5-8\n"
            "- Tier 2 ($50/mo): 10-15\n"
            "- Tier 3+ ($100/mo+): 15-25\n"
            "Higher values reduce latency but risk rate limits; monitor 429s."
        ),
    )
    geocoding_provider: str = Field(
        default="google", description="Geocoding provider: google|mapbox|mock"
    )
    google_maps_api_key: SecretStr = Field(
        default=SecretStr(""), description="Google Maps API key for geocoding/places"
    )
    mapbox_access_token: SecretStr = Field(
        default=SecretStr(""), description="Mapbox access token for geocoding/search"
    )
