from app.utils.identity import clean_identity_value, normalize_name, redact_name


def test_clean_identity_value_strips_and_handles_empty() -> None:
    assert clean_identity_value("  Johnson  ") == "Johnson"
    assert clean_identity_value("   ") is None
    assert clean_identity_value(None) is None


def test_normalize_name_lowercases_trimmed_values() -> None:
    assert normalize_name("  JOHNSON ") == "johnson"
    assert normalize_name("") is None
    assert normalize_name(None) is None


def test_redact_name_masks_value_and_empty_inputs() -> None:
    assert redact_name("Johnson") == "J****(7)"
    assert redact_name("  Li ") == "L****(2)"
    assert redact_name("") == "<empty>"
    assert redact_name(None) == "<empty>"
