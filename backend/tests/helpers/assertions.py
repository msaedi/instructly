from __future__ import annotations

from typing import Any, Callable, Iterable


def sort_then(items: Iterable[Any], key: Callable[[Any], Any]) -> list[Any]:
    """Return a sorted list built from the iterable using the provided key."""
    return sorted(list(items), key=key)


def sort_by_dict_key(items: Iterable[dict], *keys: str) -> list[dict]:
    """Sort dictionaries by the provided key sequence and return a new list."""

    def _key(dictionary: dict) -> tuple[Any, ...]:
        return tuple(dictionary.get(field) for field in keys)

    return sorted(list(items), key=_key)
