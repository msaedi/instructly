"""
Unit tests for BioGenerationService.
Uses mocks to avoid actual OpenAI API calls.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import NotFoundException, ServiceException
from app.services.bio_generation_service import BIO_CIRCUIT, BioGenerationService


@pytest.fixture(autouse=True)
def reset_circuit():
    """Reset circuit breaker before each test."""
    BIO_CIRCUIT.reset()
    yield
    BIO_CIRCUIT.reset()


def _make_service(profile=None):
    """Create BioGenerationService with mocked DB."""
    db = MagicMock()
    svc = BioGenerationService(db)
    if profile is not None:
        with patch.object(svc, "_load_profile_with_details", return_value=profile):
            return svc, db
    return svc, db


def _mock_profile(
    *,
    bio="",
    years_experience=5,
    first_name="Sarah",
    services=None,
    service_areas=None,
):
    """Build a mock instructor profile with user and optional services/areas."""
    user = SimpleNamespace(
        first_name=first_name,
        service_areas=service_areas or [],
    )

    if services is None:
        catalog_entry = SimpleNamespace(name="Piano")
        format_price = SimpleNamespace(format="online")
        service_obj = SimpleNamespace(
            catalog_entry=catalog_entry,
            format_prices=[format_price],
            is_active=True,
        )
        services = [service_obj]

    profile = SimpleNamespace(
        bio=bio,
        years_experience=years_experience,
        user=user,
        instructor_services=services,
    )
    # active_services property equivalent
    profile.active_services = [s for s in services if getattr(s, "is_active", True)]

    return profile


class TestBuildPrompt:
    """Tests for the prompt builder."""

    def test_full_context(self):
        """Prompt includes all available context."""
        neighborhood = SimpleNamespace(region_name="Upper East Side")
        service_area = SimpleNamespace(neighborhood=neighborhood)
        profile = _mock_profile(
            first_name="Sarah",
            years_experience=10,
            bio="I love teaching.",
            service_areas=[service_area],
        )

        prompt = BioGenerationService._build_prompt(profile, profile.user)

        assert "Sarah" in prompt
        assert "Piano" in prompt
        assert "10 years" in prompt
        assert "Upper East Side" in prompt
        assert "I love teaching." in prompt
        assert "teaches online" in prompt
        assert "950 characters" in prompt

    def test_sparse_profile(self):
        """Sparse profile (no services, no areas) produces valid prompt."""
        profile = _mock_profile(
            first_name="Alex",
            years_experience=None,
            services=[],
            service_areas=[],
        )

        prompt = BioGenerationService._build_prompt(profile, profile.user)

        assert "Alex" in prompt
        assert "950 characters" in prompt
        assert "who teaches" not in prompt
        assert "years of experience" not in prompt
        assert "They offer:" not in prompt
        assert "They teach in:" not in prompt

    def test_missing_first_name(self):
        """Missing first name falls back gracefully."""
        profile = _mock_profile(first_name=None, services=[])
        prompt = BioGenerationService._build_prompt(profile, profile.user)
        assert "an instructor" in prompt

    def test_with_existing_bio(self):
        """Existing bio is included for improvement."""
        profile = _mock_profile(bio="My existing bio text here.")
        prompt = BioGenerationService._build_prompt(profile, profile.user)
        assert "My existing bio text here." in prompt
        assert "Their current bio is:" in prompt

    def test_without_existing_bio(self):
        """Empty bio is not included in prompt."""
        profile = _mock_profile(bio="")
        prompt = BioGenerationService._build_prompt(profile, profile.user)
        assert "Their current bio is:" not in prompt

    def test_multiple_formats(self):
        """Multiple formats are listed."""
        fp1 = SimpleNamespace(format="student_location")
        fp2 = SimpleNamespace(format="online")
        svc = SimpleNamespace(
            catalog_entry=SimpleNamespace(name="Guitar"),
            format_prices=[fp1, fp2],
            is_active=True,
        )
        profile = _mock_profile(services=[svc])
        prompt = BioGenerationService._build_prompt(profile, profile.user)
        assert "teaches online" in prompt
        assert "travels to students" in prompt


class TestGenerateBio:
    """Tests for the generate_bio method."""

    @pytest.mark.asyncio
    async def test_returns_bio_string(self):
        """Successful generation returns a bio string."""
        profile = _mock_profile()
        svc, _db = _make_service()

        with (
            patch.object(svc, "_load_profile_with_details", return_value=profile),
            patch.object(svc, "_call_openai", new_callable=AsyncMock, return_value="I teach piano with 5 years of experience."),
        ):
            result = await svc.generate_bio("user-123")

        assert isinstance(result, str)
        assert "piano" in result.lower()

    @pytest.mark.asyncio
    async def test_no_instructor_profile(self):
        """User without profile raises NotFoundException."""
        svc, _db = _make_service()

        with patch.object(svc, "_load_profile_with_details", return_value=None):
            with pytest.raises(NotFoundException):
                await svc.generate_bio("user-no-profile")

    @pytest.mark.asyncio
    async def test_handles_openai_timeout(self):
        """OpenAI timeout raises ServiceException."""
        profile = _mock_profile()
        svc, _db = _make_service()

        async def slow_call(*_args, **_kwargs):
            await asyncio.sleep(30)

        with (
            patch.object(svc, "_load_profile_with_details", return_value=profile),
            patch.object(svc, "_call_openai", side_effect=slow_call),
        ):
            with pytest.raises(ServiceException, match="timed out"):
                await svc.generate_bio("user-123")

    @pytest.mark.asyncio
    async def test_handles_circuit_open(self):
        """Open circuit raises ServiceException."""
        profile = _mock_profile()
        svc, _db = _make_service()

        # Force circuit open
        from app.services.search.circuit_breaker import CircuitState

        BIO_CIRCUIT._state = CircuitState.OPEN

        with patch.object(svc, "_load_profile_with_details", return_value=profile):
            with pytest.raises(ServiceException, match="temporarily unavailable"):
                await svc.generate_bio("user-123")

    @pytest.mark.asyncio
    async def test_sparse_profile_still_works(self):
        """Sparse profile (no services/areas) generates successfully."""
        profile = _mock_profile(
            first_name="Alex",
            years_experience=None,
            services=[],
            service_areas=[],
        )
        svc, _db = _make_service()

        with (
            patch.object(svc, "_load_profile_with_details", return_value=profile),
            patch.object(svc, "_call_openai", new_callable=AsyncMock, return_value="A warm and welcoming instructor."),
        ):
            result = await svc.generate_bio("user-123")

        assert isinstance(result, str)
        assert len(result) > 0
