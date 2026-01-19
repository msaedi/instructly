from __future__ import annotations

from types import SimpleNamespace

from app.services.search import typo_correction


def test_load_location_alias_tokens_file_missing(monkeypatch):
    typo_correction.load_location_alias_tokens.cache_clear()

    class _DummyPath:
        def read_text(self, *args, **kwargs):
            raise FileNotFoundError("missing")

    monkeypatch.setattr(typo_correction, "LOCATION_ALIASES_JSON_PATH", _DummyPath())
    assert typo_correction.load_location_alias_tokens() == frozenset()


def test_load_location_alias_tokens_invalid_payload(monkeypatch):
    typo_correction.load_location_alias_tokens.cache_clear()

    class _DummyPath:
        def read_text(self, *args, **kwargs):
            return '{"aliases": "bad"}'

    monkeypatch.setattr(typo_correction, "LOCATION_ALIASES_JSON_PATH", _DummyPath())
    assert typo_correction.load_location_alias_tokens() == frozenset()


def test_load_location_alias_tokens_invalid_json(monkeypatch):
    typo_correction.load_location_alias_tokens.cache_clear()

    class _DummyPath:
        def read_text(self, *args, **kwargs):
            return "{not-json}"

    monkeypatch.setattr(typo_correction, "LOCATION_ALIASES_JSON_PATH", _DummyPath())
    assert typo_correction.load_location_alias_tokens() == frozenset()


def test_load_location_alias_tokens_skips_invalid_rows(monkeypatch):
    typo_correction.load_location_alias_tokens.cache_clear()

    class _DummyPath:
        def read_text(self, *args, **kwargs):
            return (
                '{"aliases": [{"alias": "UES"}, "bad", {"alias": ""}, '
                '{"alias": "Multi Word"}, {"alias": "LIC"}], '
                '"ambiguous_aliases": [{"alias": null}]}'
            )

    monkeypatch.setattr(typo_correction, "LOCATION_ALIASES_JSON_PATH", _DummyPath())
    tokens = typo_correction.load_location_alias_tokens()
    assert "ues" in tokens
    assert "lic" in tokens
    assert "multi word" not in tokens


def test_correct_typos_handles_empty_and_missing_symspell(monkeypatch):
    monkeypatch.setattr(typo_correction, "get_symspell", lambda: None)
    assert typo_correction.correct_typos("", max_edit_distance=1) == ("", False)
    assert typo_correction.correct_typos("piano", max_edit_distance=1) == ("piano", False)


def test_initialize_symspell_uses_fallback(monkeypatch):
    created = []

    class _DummyPath:
        def exists(self):
            return False

    class _DummySym:
        def __init__(self, *args, **kwargs):
            self.words = {}

        def create_dictionary_entry(self, term, freq):
            created.append((term, freq))
            self.words[term] = freq

    monkeypatch.setattr(typo_correction, "SymSpell", _DummySym)
    monkeypatch.setattr(typo_correction, "DOMAIN_DICTIONARY_PATH", _DummyPath())

    sym = typo_correction._initialize_symspell()
    assert sym is not None
    assert created


def test_initialize_symspell_handles_load_failure(monkeypatch):
    class _DummyPath:
        def exists(self):
            return True

    class _DummySym:
        def load_dictionary(self, *args, **kwargs):
            raise RuntimeError("bad dict")

    monkeypatch.setattr(typo_correction, "SymSpell", lambda *args, **kwargs: _DummySym())
    monkeypatch.setattr(typo_correction, "DOMAIN_DICTIONARY_PATH", _DummyPath())
    monkeypatch.setattr(
        typo_correction, "_load_fallback_dictionary", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("fail"))
    )

    assert typo_correction._initialize_symspell() is None


def test_get_symspell_initializes_when_missing(monkeypatch):
    sentinel = object()
    typo_correction._symspell = None
    monkeypatch.setattr(typo_correction, "_initialize_symspell", lambda: sentinel)
    assert typo_correction.get_symspell() is sentinel


def test_correct_typos_skips_protected_and_time_tokens(monkeypatch):
    class FakeSym:
        def __init__(self):
            self.calls = []

        def lookup(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return []

    sym = FakeSym()
    monkeypatch.setattr(typo_correction, "get_symspell", lambda: sym)
    monkeypatch.setattr(typo_correction, "PROTECTED_TOKENS", frozenset({"ues"}))

    corrected, was_corrected = typo_correction.correct_typos("ues 5pm in", max_edit_distance=1)
    assert corrected == "ues 5pm in"
    assert was_corrected is False
    assert sym.calls == []


def test_correct_typos_skips_short_numeric_and_stop_words(monkeypatch):
    calls = []

    class FakeSym:
        def lookup(self, *args, **kwargs):
            calls.append(args[0])
            return []

    monkeypatch.setattr(typo_correction, "get_symspell", lambda: FakeSym())
    corrected, was_corrected = typo_correction.correct_typos("a 123 $50 in")
    assert corrected == "a 123 $50 in"
    assert was_corrected is False
    assert calls == []


def test_correct_typos_skips_stop_word_and_time_token(monkeypatch):
    calls = []

    class FakeSym:
        def lookup(self, word, *_args, **_kwargs):
            calls.append(word)
            return []

    monkeypatch.setattr(typo_correction, "get_symspell", lambda: FakeSym())
    corrected, was_corrected = typo_correction.correct_typos("near 10pm")
    assert corrected == "near 10pm"
    assert was_corrected is False
    assert calls == []


def test_correct_typos_applies_suggestions(monkeypatch):
    class FakeSym:
        def lookup(self, word, *_args, **_kwargs):
            if word == "paino":
                return [SimpleNamespace(distance=1, term="piano")]
            return []

    monkeypatch.setattr(typo_correction, "get_symspell", lambda: FakeSym())
    corrected, was_corrected = typo_correction.correct_typos("paino lessons")
    assert corrected == "piano lessons"
    assert was_corrected is True


def test_correct_typos_keeps_when_distance_zero(monkeypatch):
    class FakeSym:
        def lookup(self, word, *_args, **_kwargs):
            return [SimpleNamespace(distance=0, term="piano")]

    monkeypatch.setattr(typo_correction, "get_symspell", lambda: FakeSym())
    corrected, was_corrected = typo_correction.correct_typos("piano")
    assert corrected == "piano"
    assert was_corrected is False


def test_correct_typos_clamps_distance(monkeypatch):
    seen = {}

    class FakeSym:
        def lookup(self, word, *_args, **kwargs):
            seen["max_edit_distance"] = kwargs.get("max_edit_distance")
            return []

    monkeypatch.setattr(typo_correction, "get_symspell", lambda: FakeSym())
    typo_correction.correct_typos("piano", max_edit_distance=5)
    assert seen["max_edit_distance"] == typo_correction.MAX_EDIT_DISTANCE


def test_suggest_correction_uses_correct_typos(monkeypatch):
    monkeypatch.setattr(typo_correction, "correct_typos", lambda *_args, **_kwargs: ("ok", True))
    assert typo_correction.suggest_correction("x") == "ok"

    monkeypatch.setattr(typo_correction, "correct_typos", lambda *_args, **_kwargs: ("x", False))
    assert typo_correction.suggest_correction("x") is None


def test_correct_typos_cached_delegates(monkeypatch):
    monkeypatch.setattr(typo_correction, "correct_typos", lambda *_args, **_kwargs: ("ok", True))
    assert typo_correction.correct_typos_cached("ok") == ("ok", True)
