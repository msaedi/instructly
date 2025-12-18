#!/usr/bin/env python3
"""Quick local check for SymSpell dictionary size and behavior."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tracemalloc


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    backend_root = repo_root / "backend"
    sys.path.insert(0, str(backend_root))

    import psutil  # type: ignore[import-not-found]

    proc = psutil.Process(os.getpid())
    rss_process_start = proc.memory_info().rss

    # Force SymSpell to skip import-time init so we can measure init cost explicitly.
    pytest_env = os.environ.get("PYTEST_CURRENT_TEST")
    os.environ["PYTEST_CURRENT_TEST"] = "1"
    try:
        from app.services.search.typo_correction import correct_typos, get_symspell
    finally:
        if pytest_env is None:
            os.environ.pop("PYTEST_CURRENT_TEST", None)
        else:
            os.environ["PYTEST_CURRENT_TEST"] = pytest_env

    rss_after_imports = proc.memory_info().rss

    tracemalloc.start()
    sym = get_symspell()
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    rss_after_symspell = proc.memory_info().rss

    print(f"RSS delta (imports): {(rss_after_imports - rss_process_start) / 1024 / 1024:.2f} MB")
    print(
        f"RSS delta (SymSpell init): {(rss_after_symspell - rss_after_imports) / 1024 / 1024:.2f} MB"
    )
    print(f"tracemalloc: current={current / 1024:.1f} KB peak={peak / 1024:.1f} KB")
    print(f"words: {len(sym.words) if sym else 0}")
    print(f"deletes: {len(sym._deletes) if sym else 0}")

    tests = [
        ("paino", "piano"),
        ("guittar", "guitar"),
        ("voilin", "violin"),
        ("drumms", "drums"),
        ("swiming", "swimming"),
        ("mathmatics", "mathematics"),
        ("brookyln", "brooklyn"),
    ]

    print("\nTypo correction tests:")
    for typo, expected in tests:
        corrected, _ = correct_typos(typo)
        if corrected == expected:
            status = "OK "
        elif corrected == typo:
            status = "MISS"
        else:
            status = "DIFF"
        print(f"  {status}: {typo!r} -> {corrected!r} (expected {expected!r})")


if __name__ == "__main__":
    main()
