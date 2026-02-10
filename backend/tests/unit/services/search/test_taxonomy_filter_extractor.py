from __future__ import annotations

from app.services.search import taxonomy_filter_extractor as extractor
from app.services.search.taxonomy_filter_extractor import extract_inferred_filters


def _definition(
    *,
    key: str,
    options: list[tuple[str, str]],
) -> dict[str, object]:
    return {
        "filter_key": key,
        "filter_display_name": key.replace("_", " ").title(),
        "filter_type": "multi_select",
        "options": [
            {
                "value": value,
                "display_name": display_name,
            }
            for value, display_name in options
        ],
    }


def test_extracts_course_level_from_ap_math_phrase() -> None:
    definitions = [
        _definition(
            key="course_level",
            options=[("regular", "Regular"), ("honors", "Honors"), ("ap", "AP")],
        ),
        _definition(
            key="goal",
            options=[("test_prep", "Test Prep"), ("enrichment", "Enrichment")],
        ),
    ]

    inferred = extract_inferred_filters(
        original_query="AP math in upper east side",
        filter_definitions=definitions,
        existing_explicit_filters={},
    )

    assert inferred == {"course_level": ["ap"]}


def test_phrase_precision_matches_college_prep_but_not_college_token() -> None:
    definitions = [
        _definition(
            key="goal",
            options=[("college_prep", "College Prep"), ("test_prep", "Test Prep")],
        )
    ]

    inferred_phrase = extract_inferred_filters(
        original_query="college prep math tutoring",
        filter_definitions=definitions,
    )
    inferred_token = extract_inferred_filters(
        original_query="college math tutoring",
        filter_definitions=definitions,
    )

    assert inferred_phrase == {"goal": ["college_prep"]}
    assert inferred_token == {}


def test_normalizes_hyphen_underscore_and_spaces() -> None:
    definitions = [
        _definition(
            key="format",
            options=[("one_on_one", "One-on-One"), ("small_group", "Small Group")],
        )
    ]

    inferred = extract_inferred_filters(
        original_query="Looking for one on one yoga sessions",
        filter_definitions=definitions,
    )

    assert inferred == {"format": ["one_on_one"]}


def test_explicit_filter_keys_take_precedence_over_inference() -> None:
    definitions = [
        _definition(
            key="course_level",
            options=[("regular", "Regular"), ("honors", "Honors"), ("ap", "AP")],
        )
    ]

    inferred = extract_inferred_filters(
        original_query="AP math",
        filter_definitions=definitions,
        existing_explicit_filters={"course_level": ["honors"]},
    )

    assert inferred == {}


def test_ambiguous_token_match_is_skipped() -> None:
    definitions = [
        _definition(key="style", options=[("classical", "Classical")]),
        _definition(key="goal", options=[("classical", "Classical Goal")]),
    ]

    inferred = extract_inferred_filters(
        original_query="classical piano",
        filter_definitions=definitions,
    )

    assert inferred == {}


def test_skips_skill_level_when_parser_already_derived_it() -> None:
    definitions = [
        _definition(
            key="skill_level",
            options=[
                ("beginner", "Beginner"),
                ("intermediate", "Intermediate"),
                ("advanced", "Advanced"),
            ],
        )
    ]

    inferred = extract_inferred_filters(
        original_query="beginner piano lessons",
        filter_definitions=definitions,
        parser_skill_level="beginner",
    )

    assert inferred == {}


def test_empty_query_returns_empty_dict() -> None:
    definitions = [_definition(key="level", options=[("a", "A")])]
    assert (
        extract_inferred_filters(
            original_query="",
            filter_definitions=definitions,
        )
        == {}
    )
    assert (
        extract_inferred_filters(
            original_query="   ",
            filter_definitions=definitions,
        )
        == {}
    )


def test_query_without_filter_bearing_tokens_returns_empty_dict() -> None:
    definitions = [
        _definition(
            key="goal",
            options=[("test_prep", "Test Prep"), ("enrichment", "Enrichment")],
        )
    ]

    inferred = extract_inferred_filters(
        original_query="Need a tutor near downtown after school",
        filter_definitions=definitions,
    )

    assert inferred == {}


def test_boundary_negatives_do_not_match_partial_tokens() -> None:
    definitions = [
        _definition(
            key="style",
            options=[("art", "Art"), ("ap", "AP")],
        )
    ]

    inferred_starting = extract_inferred_filters(
        original_query="starting drills for kids",
        filter_definitions=definitions,
    )
    inferred_application = extract_inferred_filters(
        original_query="application walkthrough",
        filter_definitions=definitions,
    )

    assert inferred_starting == {}
    assert inferred_application == {}


def test_ambiguous_phrase_across_multiple_keys_is_skipped() -> None:
    definitions = [
        _definition(key="goal", options=[("test_prep", "Test Prep")]),
        _definition(key="focus", options=[("test_prep", "Test Prep")]),
    ]

    inferred = extract_inferred_filters(
        original_query="test prep tutor",
        filter_definitions=definitions,
    )

    assert inferred == {}


def test_ignores_definitions_with_blank_keys_and_values() -> None:
    inferred = extract_inferred_filters(
        original_query="ap math",
        filter_definitions=[
            {"filter_key": " ", "options": [{"value": "ap", "display_name": "AP"}]},
            {"filter_key": "goal", "options": [{"value": "", "display_name": " "}]},
        ],
    )
    assert inferred == {}


def test_long_phrase_skipped_when_query_shorter() -> None:
    definitions = [
        _definition(
            key="goal",
            options=[("college_prep_program", "College Prep Program")],
        )
    ]
    inferred = extract_inferred_filters(
        original_query="college prep",
        filter_definitions=definitions,
    )
    assert inferred == {}


def test_same_key_multiple_values_is_ambiguous() -> None:
    definitions = [
        _definition(
            key="goal",
            options=[("test_prep", "Test"), ("test_exam", "Test")],
        )
    ]
    inferred = extract_inferred_filters(
        original_query="test tutor",
        filter_definitions=definitions,
    )
    assert inferred == {}


def test_non_alnum_only_query_returns_empty_dict() -> None:
    inferred = extract_inferred_filters(
        original_query="***___---",
        filter_definitions=[_definition(key="goal", options=[("x", "X")])],
    )
    assert inferred == {}


def test_normalized_values_empty_after_cleanup_are_dropped(monkeypatch) -> None:
    monkeypatch.setattr(extractor, "_normalize_filter_values", lambda _values: [])
    inferred = extract_inferred_filters(
        original_query="ap math",
        filter_definitions=[_definition(key="course_level", options=[("ap", "AP")])],
    )
    assert inferred == {}
