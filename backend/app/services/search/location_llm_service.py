"""
Tier 5: LLM-based location resolution.

Use GPT to interpret complex/semantic location strings (e.g., landmarks),
mapping them onto known `region_boundaries.region_name` values.

This is intentionally the last-resort tier due to latency and cost.
Uses strict timeouts to fail fast under load (no retries).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from openai import OpenAI

from app.services.search.config import get_search_config

logger = logging.getLogger(__name__)

# Strict OpenAI timeouts for blocking sync calls.
# Fail fast rather than block threads for 5+ seconds with retries.
OPENAI_TIMEOUT_S = float(os.getenv("OPENAI_TIMEOUT_S", "2.0"))
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "0"))


_SYSTEM_PROMPT_TEMPLATE = """You resolve NYC location queries to known NYC neighborhoods.

Given a user's location query, pick the closest matching neighborhood(s) from the allowed list.

Rules:
- Return ONLY neighborhood names from the allowed list (exact string match).
- If the query is a landmark (e.g., "museum mile"), map it to the nearest neighborhood(s).
- If ambiguous, return multiple plausible neighborhoods (max 5).
- If you cannot map it confidently, return an empty list.

Allowed neighborhood names:
{neighborhoods}

Respond with JSON only:
{{
  "neighborhoods": ["Neighborhood Name 1", "Neighborhood Name 2"],
  "confidence": 0.0,
  "reason": "short reason"
}}
"""


class LocationLLMService:
    """LLM helper to map freeform location text to region_boundaries names."""

    def __init__(self) -> None:
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                timeout=OPENAI_TIMEOUT_S,
                max_retries=OPENAI_MAX_RETRIES,
            )
        return self._client

    def resolve(
        self,
        *,
        location_text: str,
        allowed_region_names: List[str],
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve a location string via LLM.

        Returns:
            {"neighborhoods": [...], "confidence": float, "reason": str} or None
        """
        normalized = " ".join(str(location_text or "").strip().split())
        if not normalized:
            return None

        if not allowed_region_names:
            return None

        if not os.getenv("OPENAI_API_KEY"):
            return None

        config = get_search_config()
        model = config.parsing_model

        # Keep prompt size bounded: region_boundaries is ~300 rows for NYC, safe to include.
        neighborhoods_block = "\n".join(f"- {name}" for name in allowed_region_names)
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(neighborhoods=neighborhoods_block)

        try:
            request_kwargs: Dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Location query: {normalized}"},
                ],
                "response_format": {"type": "json_object"},
            }
            # GPT-5 models require `max_completion_tokens` (not `max_tokens`) and currently only
            # support default temperature.
            if not str(model).startswith("gpt-5"):
                request_kwargs["temperature"] = 0.1
                request_kwargs["max_tokens"] = 250
            else:
                request_kwargs["max_completion_tokens"] = 250

            response = self.client.chat.completions.create(**request_kwargs)
            content = response.choices[0].message.content
            if not content:
                return None

            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                return None

            neighborhoods = parsed.get("neighborhoods")
            if not isinstance(neighborhoods, list):
                return None

            confidence = parsed.get("confidence")
            try:
                confidence_val = float(confidence) if confidence is not None else 0.5
            except Exception:
                confidence_val = 0.5

            # De-dupe while preserving order; cap to 5.
            out_names: List[str] = []
            seen: set[str] = set()
            allowed_lower = {n.lower(): n for n in allowed_region_names}
            for item in neighborhoods:
                if not isinstance(item, str):
                    continue
                key = item.strip().lower()
                canonical = allowed_lower.get(key)
                if not canonical:
                    continue
                if canonical.lower() in seen:
                    continue
                seen.add(canonical.lower())
                out_names.append(canonical)
                if len(out_names) >= 5:
                    break

            if not out_names:
                return None

            return {
                "neighborhoods": out_names,
                "confidence": max(0.0, min(1.0, confidence_val)),
                "reason": str(parsed.get("reason") or ""),
            }
        except Exception as exc:
            logger.debug("Location LLM resolution failed for '%s': %s", normalized, str(exc))
            return None
