# backend/app/services/search/llm_schema.py
"""
Pydantic schema for LLM structured output parsing.
Used with OpenAI's beta.chat.completions.parse() method.
"""
from typing import Literal, Optional

from pydantic import ConfigDict, Field

from app.schemas._strict_base import StrictModel


class LLMParsedQuery(StrictModel):
    """
    Schema for LLM structured output.

    This schema is passed to OpenAI's parse() method which ensures
    the response conforms to this structure.
    """

    model_config = ConfigDict(extra="forbid")

    # Required field
    service_query: str = Field(
        description=(
            "The type of lesson/service being searched for "
            "(e.g., 'piano lessons', 'math tutoring'). Correct obvious typos."
        )
    )

    # Price constraints
    max_price: Optional[int] = Field(
        default=None,
        description=(
            "Maximum price per hour in dollars. " "Extract from 'under $X', 'cheap', 'budget', etc."
        ),
    )
    min_price: Optional[int] = Field(
        default=None,
        description=(
            "Minimum price per hour in dollars. " "Extract from 'at least $X', 'premium', etc."
        ),
    )

    # Date constraints
    date: Optional[str] = Field(
        default=None,
        description=(
            "Specific date in YYYY-MM-DD format. " "Convert relative dates like 'tomorrow'."
        ),
    )
    date_range_start: Optional[str] = Field(
        default=None,
        description="Start of date range in YYYY-MM-DD format.",
    )
    date_range_end: Optional[str] = Field(
        default=None,
        description="End of date range in YYYY-MM-DD format.",
    )

    # Time constraints
    time_after: Optional[str] = Field(
        default=None,
        description=("Earliest time in HH:MM 24-hour format. " "Convert 'after 5pm' to '17:00'."),
    )
    time_before: Optional[str] = Field(
        default=None,
        description=("Latest time in HH:MM 24-hour format. " "Convert 'before 3pm' to '15:00'."),
    )

    # Location
    location: Optional[str] = Field(
        default=None,
        description="NYC borough or neighborhood name. Normalize to proper case.",
    )

    # Audience and skill
    audience_hint: Optional[Literal["kids", "adults"]] = Field(
        default=None,
        description=(
            "'kids' if query mentions children/kids/teens/age under 18, "
            "'adults' if explicitly for adults. Used for ranking boost only."
        ),
    )
    skill_level: Optional[Literal["beginner", "intermediate", "advanced"]] = Field(
        default=None,
        description="Skill level mentioned in query.",
    )

    # Urgency
    urgency: Optional[Literal["high", "medium", "low"]] = Field(
        default=None,
        description="'high' for urgent/asap, 'medium' for soon, 'low' otherwise.",
    )

    # 3-level taxonomy hints
    category_hint: Optional[
        Literal[
            "Tutoring & Test Prep",
            "Music",
            "Dance",
            "Languages",
            "Sports & Fitness",
            "Arts",
            "Hobbies & Life Skills",
        ]
    ] = Field(
        default=None,
        description="Primary category the user is searching in.",
    )

    subcategory_hint: Optional[str] = Field(
        default=None,
        description=(
            "Specific subcategory within the category (e.g., 'Martial Arts' within "
            "Sports & Fitness, 'Test Prep' within Tutoring & Test Prep). "
            "Only include if the query clearly targets a subcategory."
        ),
    )

    service_hint: Optional[str] = Field(
        default=None,
        description=(
            "Specific service name if the query targets an exact service "
            "(e.g., 'Karate', 'SAT', 'Piano'). "
            "Only include if the query names a specific bookable service."
        ),
    )
