"""Generate search keyword dictionaries from seeded taxonomy data."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import logging
from pathlib import Path
import re
import threading
from typing import Sequence

from sqlalchemy.orm import Session

from app.repositories.category_repository import CategoryRepository
from app.repositories.service_catalog_repository import ServiceCatalogRepository
from app.repositories.subcategory_repository import SubcategoryRepository

logger = logging.getLogger(__name__)


class KeywordDictCache:
    """Thread-safe cache for generated keyword dictionaries."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._dicts: dict[str, dict[str, str]] | None = None
        self._source: str | None = None

    def invalidate(self) -> None:
        """Clear cached dictionaries so the next read rebuilds from source."""
        with self._lock:
            self._dicts = None
            self._source = None

    def get(
        self,
        db: Session | None = None,
        *,
        force_refresh: bool = False,
    ) -> dict[str, dict[str, str]]:
        with self._lock:
            should_use_cache = self._dicts is not None and not force_refresh
            if should_use_cache and (db is None or self._source == "db"):
                cached = self._dicts
                if cached is None:
                    raise RuntimeError("keyword cache unexpectedly missing")
                # Returned dictionaries are treated as read-only by callers.
                return cached

            if db is None:
                categories, subcategories, services = _load_taxonomy_from_seed()
                generated = _build_keyword_dicts(categories, subcategories, services)
                self._source = "seed"
            else:
                try:
                    generated = generate_keyword_dicts(db)
                    self._source = "db"
                except Exception as exc:
                    logger.warning(
                        "search_keyword_generation_from_db_failed",
                        extra={"error": str(exc)},
                    )
                    categories, subcategories, services = _load_taxonomy_from_seed()
                    generated = _build_keyword_dicts(categories, subcategories, services)
                    self._source = "seed"

            self._dicts = generated
            return generated


_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
}

# Keep only non-derivable aliases here.
_CURATED_SERVICE_SYNONYMS: dict[str, str] = {
    "bjj": "Jiu-Jitsu",
    "jiu jitsu": "Jiu-Jitsu",
    "jiu-jitsu": "Jiu-Jitsu",
    "dj": "DJing",
}

_CURATED_CATEGORY_SYNONYMS: dict[str, str] = {
    "tutor": "Tutoring & Test Prep",
    "tutors": "Tutoring & Test Prep",
}


@dataclass(frozen=True)
class _CategoryRow:
    name: str
    slug: str | None


@dataclass(frozen=True)
class _SubcategoryRow:
    name: str
    slug: str | None
    category_name: str


@dataclass(frozen=True)
class _ServiceRow:
    name: str
    slug: str | None
    subcategory_name: str
    category_name: str


def _normalize_text(raw: str, *, keep_hyphen: bool) -> str:
    value = (raw or "").strip().lower()
    value = value.replace("&", " and ").replace("/", " ")
    if not keep_hyphen:
        value = value.replace("-", " ")
    pattern = r"[^a-z0-9\s-]" if keep_hyphen else r"[^a-z0-9\s]"
    value = re.sub(pattern, " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _slugify_seed(name: str) -> str:
    normalized = _normalize_text(name, keep_hyphen=False)
    return normalized.replace(" ", "-")


def _add_keyword(target: set[str], keyword: str) -> None:
    key = keyword.strip().lower()
    if len(key) < 2:
        return
    target.add(key)


def _phrase_keywords(name: str, slug: str | None) -> set[str]:
    keywords: set[str] = set()

    raw_values: list[str] = [name]
    if slug:
        raw_values.extend([slug, slug.replace("-", " ")])

    for raw in raw_values:
        _add_keyword(keywords, _normalize_text(raw, keep_hyphen=True))
        _add_keyword(keywords, _normalize_text(raw, keep_hyphen=False))

    # Parenthetical phrases (e.g. "ISR (Infant Self-Rescue)").
    for chunk in re.findall(r"\(([^)]+)\)", name):
        for part in re.split(r"[,/]", chunk):
            normalized = _normalize_text(part, keep_hyphen=False)
            _add_keyword(keywords, normalized)
            tokens = [t for t in normalized.split() if t and t not in _STOPWORDS]
            if len(tokens) >= 2:
                acronym = "".join(t[0] for t in tokens)
                _add_keyword(keywords, acronym)

    leading_acronym = re.match(r"^([A-Za-z]{2,8})\s*\(", name.strip())
    if leading_acronym:
        _add_keyword(keywords, leading_acronym.group(1))

    normalized_name = _normalize_text(name, keep_hyphen=False)
    tokens = [t for t in normalized_name.split() if t and t not in _STOPWORDS]

    # Single token variants + singularized forms.
    for token in tokens:
        if len(token) >= 3 or token in {"ai", "isr"}:
            _add_keyword(keywords, token)
            if token.endswith("s") and len(token) > 3:
                _add_keyword(keywords, token[:-1])

    # Multi-token variants (up to trigrams).
    for ngram_len in (2, 3):
        if len(tokens) < ngram_len:
            continue
        for idx in range(len(tokens) - ngram_len + 1):
            gram = tokens[idx : idx + ngram_len]
            _add_keyword(keywords, " ".join(gram))

    # Compact variant for short multiword names like "k pop" -> "kpop".
    if 2 <= len(tokens) <= 3 and all(len(t) <= 6 for t in tokens):
        _add_keyword(keywords, "".join(tokens))

    return keywords


def _load_taxonomy_from_db(
    db: Session,
) -> tuple[list[_CategoryRow], list[_SubcategoryRow], list[_ServiceRow]]:
    category_repo = CategoryRepository(db)
    subcategory_repo = SubcategoryRepository(db)
    service_repo = ServiceCatalogRepository(db)

    categories = category_repo.get_all_active(include_subcategories=False)
    category_rows = [
        _CategoryRow(name=category.name, slug=category.slug) for category in categories
    ]

    subcategory_rows: list[_SubcategoryRow] = []
    for category in categories:
        for subcategory in subcategory_repo.get_by_category(category.id, active_only=True):
            subcategory_rows.append(
                _SubcategoryRow(
                    name=subcategory.name,
                    slug=subcategory.slug,
                    category_name=category.name,
                )
            )

    service_rows: list[_ServiceRow] = []
    for service in service_repo.list_services_with_categories(include_inactive=False):
        subcategory = service.subcategory
        if subcategory is None or not subcategory.is_active:
            continue
        category = subcategory.category
        if category is None:
            continue
        service_rows.append(
            _ServiceRow(
                name=service.name,
                slug=service.slug,
                subcategory_name=subcategory.name,
                category_name=category.name,
            )
        )

    if not category_rows or not subcategory_rows or not service_rows:
        raise ValueError("taxonomy tables returned no rows")

    return category_rows, subcategory_rows, service_rows


def _load_taxonomy_from_seed() -> (
    tuple[list[_CategoryRow], list[_SubcategoryRow], list[_ServiceRow]]
):
    seed_path = Path(__file__).resolve().parents[3] / "scripts" / "seed_data" / "seed_taxonomy.py"
    spec = importlib.util.spec_from_file_location("seed_taxonomy", seed_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"unable to load seed taxonomy module: {seed_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    categories = [
        _CategoryRow(name=str(entry["name"]), slug=str(entry.get("slug") or ""))
        for entry in getattr(module, "CATEGORIES")
    ]

    subcategories: list[_SubcategoryRow] = []
    services: list[_ServiceRow] = []

    taxonomy: dict[str, list[tuple[str, int, list[str]]]] = getattr(module, "TAXONOMY")
    for category_name, sub_rows in taxonomy.items():
        for sub_name, _order, service_names in sub_rows:
            subcategories.append(
                _SubcategoryRow(
                    name=sub_name,
                    slug=_slugify_seed(sub_name),
                    category_name=category_name,
                )
            )
            for service_name in service_names:
                services.append(
                    _ServiceRow(
                        name=service_name,
                        slug=_slugify_seed(service_name),
                        subcategory_name=sub_name,
                        category_name=category_name,
                    )
                )

    return categories, subcategories, services


def _build_keyword_dicts(
    categories: Sequence[_CategoryRow],
    subcategories: Sequence[_SubcategoryRow],
    services: Sequence[_ServiceRow],
) -> dict[str, dict[str, str]]:
    service_keywords: dict[str, str] = {}
    subcategory_keywords: dict[str, str] = {}
    category_keywords: dict[str, str] = {}

    subcategory_to_category = {row.name: row.category_name for row in subcategories}
    service_to_parent = {row.name: (row.subcategory_name, row.category_name) for row in services}

    for category_row in categories:
        for keyword in _phrase_keywords(category_row.name, category_row.slug):
            category_keywords.setdefault(keyword, category_row.name)

    for subcategory_row in subcategories:
        for keyword in _phrase_keywords(subcategory_row.name, subcategory_row.slug):
            subcategory_keywords.setdefault(keyword, subcategory_row.name)

    for service_row in services:
        for keyword in _phrase_keywords(service_row.name, service_row.slug):
            existing = service_keywords.get(keyword)
            if existing is None:
                service_keywords[keyword] = service_row.name
                continue

            existing_exact = _normalize_text(existing, keep_hyphen=False) == keyword
            candidate_exact = _normalize_text(service_row.name, keep_hyphen=False) == keyword
            if candidate_exact and not existing_exact:
                service_keywords[keyword] = service_row.name

    # Curated aliases for non-derivable terms.
    for keyword, service_name in _CURATED_SERVICE_SYNONYMS.items():
        if service_name in service_to_parent:
            service_keywords[keyword] = service_name

    available_categories = {row.name for row in categories}
    for keyword, curated_category_name in _CURATED_CATEGORY_SYNONYMS.items():
        if curated_category_name in available_categories:
            category_keywords[keyword] = curated_category_name

    # Ensure service and subcategory keys always carry consistent parent category.
    for keyword, subcategory_name in subcategory_keywords.items():
        parent_category_name = subcategory_to_category.get(subcategory_name)
        if parent_category_name:
            category_keywords[keyword] = parent_category_name

    for keyword, service_name in service_keywords.items():
        parent = service_to_parent.get(service_name)
        if parent is None:
            continue
        subcategory_name, category_name = parent
        subcategory_keywords[keyword] = subcategory_name
        category_keywords[keyword] = category_name

    return {
        "category_keywords": dict(sorted(category_keywords.items())),
        "subcategory_keywords": dict(sorted(subcategory_keywords.items())),
        "service_keywords": dict(sorted(service_keywords.items())),
    }


def generate_keyword_dicts(db: Session) -> dict[str, dict[str, str]]:
    """Generate category/subcategory/service keyword dictionaries from taxonomy rows."""
    categories, subcategories, services = _load_taxonomy_from_db(db)
    return _build_keyword_dicts(categories, subcategories, services)


_keyword_dict_cache = KeywordDictCache()


def get_keyword_dicts(
    db: Session | None = None,
    *,
    force_refresh: bool = False,
) -> dict[str, dict[str, str]]:
    """Return cached keyword dictionaries generated from taxonomy seed data."""
    return _keyword_dict_cache.get(db=db, force_refresh=force_refresh)


def invalidate_keyword_dict_cache() -> None:
    """Clear in-process keyword dictionaries."""
    _keyword_dict_cache.invalidate()


__all__ = ["generate_keyword_dicts", "get_keyword_dicts", "invalidate_keyword_dict_cache"]
