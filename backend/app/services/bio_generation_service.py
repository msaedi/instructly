"""
Bio generation service using OpenAI to create personalized instructor bios.

Follows the same patterns as llm_parser.py: lazy AsyncOpenAI client,
circuit breaker, and shared semaphore for concurrency control.
"""

import asyncio
import logging
from typing import Optional

from openai import AsyncOpenAI, OpenAIError
from sqlalchemy.orm import Session

from ..core.exceptions import NotFoundException, ServiceException
from ..models.instructor import InstructorProfile
from ..repositories import RepositoryFactory
from .base import BaseService
from .search.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitOpenError
from .search.openai_semaphore import OPENAI_CALL_SEMAPHORE

logger = logging.getLogger(__name__)

BIO_CIRCUIT = CircuitBreaker(
    name="bio_generation",
    config=CircuitBreakerConfig(
        failure_threshold=5,
        timeout_seconds=60.0,
        window_seconds=30.0,
    ),
)

_FORMAT_LABELS = {
    "student_location": "travels to students",
    "instructor_location": "teaches at their studio",
    "online": "teaches online",
}

_BIO_CHAR_LIMIT = 950

_REQUIREMENTS = """Requirements:
- First person ("I" not "they")
- Conversational and warm tone
- No exclamation points
- No marketing jargon or clichés
- Focus on teaching approach and what students can expect
- Do not invent credentials, degrees, or qualifications
- Do not mention the platform name
- STRICT LIMIT: stay under {char_limit} characters (roughly 120-160 words)"""

_BIO_MODEL = "gpt-5-nano"
_BIO_MAX_COMPLETION_TOKENS = 1000
_BIO_TIMEOUT_S = 15.0


class BioGenerationService(BaseService):
    """Generates personalized instructor bios via OpenAI."""

    def __init__(self, db: Session) -> None:
        super().__init__(db)
        self._client: Optional[AsyncOpenAI] = None
        self._profile_repo = RepositoryFactory.create_instructor_profile_repository(db)

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(timeout=_BIO_TIMEOUT_S, max_retries=1)
        return self._client

    def _load_profile_with_details(self, user_id: str) -> Optional[InstructorProfile]:
        return self._profile_repo.get_by_user_id_with_details(user_id)

    @BaseService.measure_operation("generate_instructor_bio")
    async def generate_bio(self, user_id: str) -> str:
        profile = await asyncio.to_thread(self._load_profile_with_details, user_id)
        if profile is None:
            raise NotFoundException("Instructor profile not found")

        user = profile.user
        prompt = self._build_prompt(profile, user)

        if BIO_CIRCUIT.is_open:
            raise ServiceException("Bio generation temporarily unavailable")

        async with OPENAI_CALL_SEMAPHORE:
            try:
                result: str = await asyncio.wait_for(
                    BIO_CIRCUIT.call(self._call_openai, prompt),
                    timeout=_BIO_TIMEOUT_S,
                )
                return result
            except asyncio.TimeoutError:
                raise ServiceException("Bio generation timed out")
            except CircuitOpenError:
                raise ServiceException("Bio generation temporarily unavailable")
            except OpenAIError as exc:
                logger.warning("OpenAI error during bio generation: %s", exc)
                raise ServiceException("Bio generation failed")

    async def _call_openai(self, prompt: str) -> str:
        response = await self.client.chat.completions.create(
            model=_BIO_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful writing assistant that creates instructor bios.",
                },
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=_BIO_MAX_COMPLETION_TOKENS,
            reasoning_effort="minimal",
        )
        content: Optional[str] = response.choices[0].message.content
        if not content:
            raise ServiceException("Bio generation returned empty response")
        return str(content).strip()

    @staticmethod
    def _build_prompt(profile: object, user: object) -> str:  # noqa: ANN001
        first_name = getattr(user, "first_name", None) or "an instructor"
        years = getattr(profile, "years_experience", None)

        active_services = getattr(profile, "active_services", None) or []
        skills = []
        for svc in active_services:
            entry = getattr(svc, "catalog_entry", None)
            if entry:
                name = getattr(entry, "name", None)
                if name:
                    skills.append(name)

        format_set: set[str] = set()
        for svc in active_services:
            for fp in getattr(svc, "format_prices", None) or []:
                fmt = getattr(fp, "format", None)
                if fmt:
                    format_set.add(fmt)

        service_areas = getattr(user, "service_areas", None) or []
        neighborhoods = []
        for sa in service_areas:
            nb = getattr(sa, "neighborhood", None)
            if nb:
                name = getattr(nb, "region_name", None)
                if name:
                    neighborhoods.append(name)

        current_bio = (getattr(profile, "bio", None) or "").strip()

        intro = f"Write a short instructor bio (under {_BIO_CHAR_LIMIT} characters) in first person for {first_name}"
        if skills:
            intro += f", who teaches {', '.join(skills)}"
        if years:
            intro += f" with {years} years of experience"
        intro += "."

        sections = [intro]

        if format_set:
            labels = [_FORMAT_LABELS.get(f, f) for f in sorted(format_set)]
            sections.append(f"They offer: {', '.join(labels)}")
        if neighborhoods:
            sections.append(f"They teach in: {', '.join(neighborhoods)}")
        if current_bio:
            sections.append(f"Their current bio is: {current_bio}")

        sections.append(_REQUIREMENTS.format(char_limit=_BIO_CHAR_LIMIT))
        return "\n\n".join(sections)
