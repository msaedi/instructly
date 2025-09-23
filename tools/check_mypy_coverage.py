#!/usr/bin/env python3
"""Guardrail to ensure mypy strict coverage globs stay in sync."""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "backend" / "pyproject.toml"

TARGETS = {
    "backend.app.repositories": ROOT / "backend" / "app" / "repositories",
    "backend.app.services": ROOT / "backend" / "app" / "services",
    "backend.app.routes": ROOT / "backend" / "app" / "routes",
}

ALLOWED_NON_STRICT = {
    "backend.app.services.stripe_service",
    "backend.app.services.base",
}


def iter_modules(base: Path, prefix: str) -> set[str]:
    modules: set[str] = set()
    for path in base.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(base)
        module = prefix + "." + rel.with_suffix("").as_posix().replace("/", ".")
        modules.add(module)
    return modules


def load_overrides() -> list[tuple[str, dict[str, object]]]:
    data = tomllib.loads(PYPROJECT.read_text())
    overrides = data.get("tool", {}).get("mypy", {}).get("overrides", [])
    ordered: list[tuple[str, dict[str, object]]] = []
    for override in overrides:
        modules = override.get("module", [])
        if isinstance(modules, str):
            modules = [modules]
        for pattern in modules:
            ordered.append((pattern, override))
    return ordered


def effective_strict(module: str, patterns: list[tuple[str, dict[str, object]]]) -> tuple[bool | None, bool]:
    matched = False
    strict: bool | None = None
    for pattern, override in patterns:
        if fnmatch.fnmatchcase(module, pattern):
            matched = True
            if "strict" in override:
                strict = bool(override["strict"])
    return strict, matched


def main() -> int:
    patterns = load_overrides()
    failures: list[str] = []

    for prefix, base in TARGETS.items():
        if not base.exists():
            continue
        for module in sorted(iter_modules(base, prefix)):
            strict, matched = effective_strict(module, patterns)
            if not matched:
                failures.append(f"{module}: missing mypy override (not covered by any pattern)")
                continue
            if module in ALLOWED_NON_STRICT:
                if strict is False:
                    continue
                failures.append(f"{module}: expected non-strict override, found strict={strict}")
                continue
            if strict is not True:
                failures.append(f"{module}: effective strict={strict} (expected True)")

    if failures:
        print("mypy strict coverage check failed:")
        for line in failures:
            print(f"  - {line}")
        return 1

    print("mypy strict coverage check passed: all target modules covered by strict overrides")
    return 0


if __name__ == "__main__":
    sys.exit(main())
