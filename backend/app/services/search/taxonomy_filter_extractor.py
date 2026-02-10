"""Helpers for inferring taxonomy filter selections from NL query text."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_FilterEntry = Tuple[str, str]


def _normalize_phrase(raw_value: str) -> str:
    """Normalize text for phrase/token matching."""
    normalized = str(raw_value).strip().lower().replace("_", " ").replace("-", " ")
    normalized = _NON_ALNUM_RE.sub(" ", normalized)
    return " ".join(normalized.split())


def _normalize_filter_values(values: Optional[Iterable[str]]) -> List[str]:
    normalized: List[str] = []
    seen: Set[str] = set()

    for raw_value in values or []:
        value = str(raw_value).strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)

    return normalized


def _build_phrase_index(filter_definitions: List[Dict[str, Any]]) -> Dict[str, Set[_FilterEntry]]:
    phrase_index: Dict[str, Set[_FilterEntry]] = {}

    for definition in filter_definitions:
        filter_key = str(definition.get("filter_key") or "").strip().lower()
        if not filter_key:
            continue

        options = definition.get("options") or []
        for option in options:
            option_value = str(option.get("value") or "").strip().lower()
            if not option_value:
                continue

            match_phrases: Set[str] = {_normalize_phrase(option_value)}
            option_display_name = str(option.get("display_name") or "").strip()
            if option_display_name:
                match_phrases.add(_normalize_phrase(option_display_name))

            for phrase in match_phrases:
                if not phrase:
                    continue
                phrase_index.setdefault(phrase, set()).add((filter_key, option_value))

    return phrase_index


def _select_match(
    entries: Set[_FilterEntry],
    *,
    blocked_keys: Set[str],
) -> Optional[_FilterEntry]:
    valid_entries = [entry for entry in entries if entry[0] not in blocked_keys]
    if not valid_entries:
        return None

    matching_keys = {key for key, _ in valid_entries}
    if len(matching_keys) != 1:
        return None

    matching_values = {value for _, value in valid_entries}
    if len(matching_values) != 1:
        return None

    return sorted(valid_entries)[0]


def extract_inferred_filters(
    *,
    original_query: str,
    filter_definitions: List[Dict[str, Any]],
    existing_explicit_filters: Optional[Dict[str, List[str]]] = None,
    parser_skill_level: Optional[str] = None,
) -> Dict[str, List[str]]:
    """Infer taxonomy filters from query text using phrase-first matching.

    Matching semantics:
      - Multi-word phrases are matched first (longest phrase wins)
      - Single-word tokens are matched after phrase extraction
      - Matching is case-insensitive and whole-word based
      - If a token/phrase maps to multiple filter keys, it is treated as ambiguous and skipped
      - Explicit filter keys always win and are never overwritten here
    """
    normalized_query = _normalize_phrase(original_query)
    if not normalized_query:
        return {}

    phrase_index = _build_phrase_index(filter_definitions)
    if not phrase_index:
        return {}

    blocked_keys: Set[str] = {
        str(raw_key).strip().lower()
        for raw_key in (existing_explicit_filters or {}).keys()
        if str(raw_key).strip()
    }
    if parser_skill_level:
        blocked_keys.add("skill_level")

    query_tokens = normalized_query.split()
    if not query_tokens:
        return {}

    inferred_filters: Dict[str, List[str]] = {}
    matched_token_indices: Set[int] = set()

    def _append_match(filter_key: str, value: str) -> None:
        values = inferred_filters.setdefault(filter_key, [])
        if value not in values:
            values.append(value)

    multi_word_phrases = sorted(
        (phrase for phrase in phrase_index.keys() if len(phrase.split()) > 1),
        key=lambda phrase: (-len(phrase.split()), -len(phrase)),
    )

    # Phrase matching first to preserve precision ("college prep" before "college").
    for phrase in multi_word_phrases:
        phrase_tokens = phrase.split()
        token_count = len(phrase_tokens)
        if token_count > len(query_tokens):
            continue

        for start_index in range(0, len(query_tokens) - token_count + 1):
            span = range(start_index, start_index + token_count)
            if any(index in matched_token_indices for index in span):
                continue
            if query_tokens[start_index : start_index + token_count] != phrase_tokens:
                continue

            selected_match = _select_match(
                phrase_index[phrase],
                blocked_keys=blocked_keys,
            )
            if selected_match is None:
                continue

            filter_key, filter_value = selected_match
            _append_match(filter_key, filter_value)
            matched_token_indices.update(span)

    for token_index, token in enumerate(query_tokens):
        if token_index in matched_token_indices:
            continue

        entries = phrase_index.get(token)
        if not entries:
            continue

        selected_match = _select_match(entries, blocked_keys=blocked_keys)
        if selected_match is None:
            continue

        filter_key, filter_value = selected_match
        _append_match(filter_key, filter_value)
        matched_token_indices.add(token_index)

    normalized_inferred: Dict[str, List[str]] = {}
    for key, values in inferred_filters.items():
        normalized_values = _normalize_filter_values(values)
        if normalized_values:
            normalized_inferred[key] = normalized_values

    return normalized_inferred
