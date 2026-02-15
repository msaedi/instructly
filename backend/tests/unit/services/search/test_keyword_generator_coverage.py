from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.search import keyword_generator as kg


def test_keyword_cache_invalidate_clears_cached_state() -> None:
    cache = kg.KeywordDictCache()
    cache._dicts = {"service_keywords": {"piano": "Piano"}}
    cache._source = "seed"

    cache.invalidate()

    assert cache._dicts is None
    assert cache._source is None


def test_keyword_cache_get_uses_cached_seed_dicts() -> None:
    cache = kg.KeywordDictCache()
    calls = {"seed": 0, "build": 0}

    def _seed_loader():
        calls["seed"] += 1
        return (
            [kg._CategoryRow(name="Music", slug="music")],
            [kg._SubcategoryRow(name="Piano", slug="piano", category_name="Music")],
            [
                kg._ServiceRow(
                    name="Piano Lessons",
                    slug="piano-lessons",
                    subcategory_name="Piano",
                    category_name="Music",
                )
            ],
        )

    def _builder(_categories, _subcategories, _services):
        calls["build"] += 1
        return {"service_keywords": {"piano": "Piano Lessons"}}

    cache_loader = _seed_loader
    cache_builder = _builder

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(kg, "_load_taxonomy_from_seed", cache_loader)
        mp.setattr(kg, "_build_keyword_dicts", cache_builder)
        first = cache.get()
        second = cache.get()

    assert first == second
    assert calls == {"seed": 1, "build": 1}


def test_keyword_cache_db_failure_falls_back_to_seed(monkeypatch) -> None:
    cache = kg.KeywordDictCache()

    def _boom(_db):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(kg, "generate_keyword_dicts", _boom)
    monkeypatch.setattr(
        kg,
        "_load_taxonomy_from_seed",
        lambda: (
            [kg._CategoryRow(name="Music", slug="music")],
            [kg._SubcategoryRow(name="Piano", slug="piano", category_name="Music")],
            [
                kg._ServiceRow(
                    name="Piano Lessons",
                    slug="piano-lessons",
                    subcategory_name="Piano",
                    category_name="Music",
                )
            ],
        ),
    )
    monkeypatch.setattr(
        kg,
        "_build_keyword_dicts",
        lambda *_args: {"service_keywords": {"piano": "Piano Lessons"}},
    )

    result = cache.get(db=object())
    assert result["service_keywords"]["piano"] == "Piano Lessons"
    assert cache._source == "seed"


def test_load_taxonomy_from_seed_raises_when_spec_missing(monkeypatch) -> None:
    monkeypatch.setattr(kg.importlib.util, "spec_from_file_location", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="unable to load seed taxonomy module"):
        kg._load_taxonomy_from_seed()


def test_load_taxonomy_from_seed_builds_rows(monkeypatch) -> None:
    class _Loader:
        def exec_module(self, module) -> None:
            module.CATEGORIES = [{"name": "Music", "slug": "music"}]
            module.TAXONOMY = {
                "Music": [
                    ("Piano", 1, ["Jazz Piano", "Classical Piano"]),
                ]
            }

    fake_spec = SimpleNamespace(loader=_Loader())
    monkeypatch.setattr(kg.importlib.util, "spec_from_file_location", lambda *_args, **_kwargs: fake_spec)
    monkeypatch.setattr(kg.importlib.util, "module_from_spec", lambda _spec: SimpleNamespace())

    categories, subcategories, services = kg._load_taxonomy_from_seed()

    assert categories[0].name == "Music"
    assert subcategories[0].name == "Piano"
    assert subcategories[0].slug == "piano"
    assert services[0].name == "Jazz Piano"
    assert services[0].slug == "jazz-piano"


def test_phrase_keywords_captures_acronyms_and_compact_forms() -> None:
    keywords = kg._phrase_keywords("ISR (Infant Self-Rescue)", "isr-infant-self-rescue")
    assert "isr" in keywords
    assert "infant self rescue" in keywords

    compact_keywords = kg._phrase_keywords("K Pop", None)
    assert "kpop" in compact_keywords


def test_build_keyword_dicts_removes_conflicting_specific_matches() -> None:
    categories = [
        kg._CategoryRow(name="Arts", slug="arts"),
        kg._CategoryRow(name="Sports & Fitness", slug="sports-fitness"),
    ]
    subcategories = [
        kg._SubcategoryRow(name="Martial Arts", slug="martial-arts", category_name="Sports & Fitness"),
    ]
    services = [
        kg._ServiceRow(
            name="Arts Coaching",
            slug="arts-coaching",
            subcategory_name="Martial Arts",
            category_name="Sports & Fitness",
        ),
    ]

    generated = kg._build_keyword_dicts(categories, subcategories, services)

    assert generated["category_keywords"]["arts"] == "Arts"
    assert "arts" not in generated["subcategory_keywords"]
    assert "arts" not in generated["service_keywords"]
