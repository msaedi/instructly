"""Shared configuration constants for NL search location resolution."""

from __future__ import annotations

import os

LOCATION_LLM_TOP_K = int(os.getenv("LOCATION_LLM_TOP_K", "5"))
LOCATION_TIER4_HIGH_CONFIDENCE = float(os.getenv("LOCATION_TIER4_HIGH_CONFIDENCE", "0.85"))
LOCATION_LLM_CONFIDENCE_THRESHOLD = float(os.getenv("LOCATION_LLM_CONFIDENCE_THRESHOLD", "0.7"))
LOCATION_LLM_EMBEDDING_THRESHOLD = float(os.getenv("LOCATION_LLM_EMBEDDING_THRESHOLD", "0.7"))
