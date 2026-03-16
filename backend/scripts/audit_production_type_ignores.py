#!/usr/bin/env python3
"""
Audit production # type: ignore usage in backend/app.

This guardrail is intentionally narrower than a repo-wide grep:
it focuses on production backend code and compares live ignores
against an explicit allowlist with reasons.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys

IGNORE_RE = re.compile(r"#\s*type:\s*ignore(?:\[(?P<code>[^\]]+)\])?")

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
NC = "\033[0m"


@dataclass(frozen=True)
class IgnoreUse:
    path: str
    line_number: int
    code: str | None
    line_text: str


@dataclass(frozen=True)
class AllowlistEntry:
    path: str
    code: str | None
    match: str
    reason: str

    @property
    def key(self) -> tuple[str, str | None, str]:
        return (self.path, self.code, self.match)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _allowlist_path() -> Path:
    return _backend_root() / "type_ignore_allowlist.json"


def _iter_production_files() -> list[Path]:
    backend_root = _backend_root()
    app_root = backend_root / "app"
    excluded = {
        app_root / "main.py",
        app_root / "openapi_app.py",
    }
    files: list[Path] = []
    for path in sorted(app_root.rglob("*.py")):
        if path in excluded:
            continue
        if any(part in {"tests", "scripts", "__pycache__", "migrations", "alembic"} for part in path.parts):
            continue
        files.append(path)
    return files


def _find_ignores() -> list[IgnoreUse]:
    backend_root = _backend_root()
    ignores: list[IgnoreUse] = []
    for path in _iter_production_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = IGNORE_RE.search(line)
            if not match:
                continue
            code = match.group("code")
            ignores.append(
                IgnoreUse(
                    path=str(path.relative_to(backend_root)).replace("\\", "/"),
                    line_number=line_number,
                    code=code.strip() if code else None,
                    line_text=line.rstrip(),
                )
            )
    return ignores


def _load_allowlist() -> list[AllowlistEntry]:
    payload = json.loads(_allowlist_path().read_text(encoding="utf-8"))
    entries: list[AllowlistEntry] = []
    for raw_entry in payload.get("entries", []):
        entries.append(
            AllowlistEntry(
                path=raw_entry["path"],
                code=raw_entry.get("code"),
                match=raw_entry["match"],
                reason=raw_entry["reason"],
            )
        )
    return entries


def _match_entry(ignore_use: IgnoreUse, entries: list[AllowlistEntry]) -> AllowlistEntry | None:
    for entry in entries:
        if entry.path != ignore_use.path:
            continue
        if entry.code != ignore_use.code:
            continue
        if entry.match not in ignore_use.line_text:
            continue
        return entry
    return None


def _print_header() -> None:
    print("🔍 Backend Production Type Ignore Audit")
    print("=======================================")


def _print_results(
    ignores: list[IgnoreUse],
    entries: list[AllowlistEntry],
    unapproved: list[IgnoreUse],
    stale: list[AllowlistEntry],
) -> None:
    print()
    print("📊 Results:")
    print(f"   Current count:     {len(ignores)}")
    print(f"   Allowlisted:       {len(entries)}")
    print(f"   Unapproved count:  {len(unapproved)}")
    print(f"   Stale entries:     {len(stale)}")
    print()


def _print_unapproved(unapproved: list[IgnoreUse]) -> None:
    if not unapproved:
        return
    print(f"{RED}❌ VIOLATION: Unapproved production # type: ignore comments detected!{NC}")
    print()
    print("New ignores found. If one is truly necessary:")
    print("  1. Fix the underlying typing issue if practical")
    print("  2. If it is a framework/tooling limitation, add a narrow allowlist entry with a reason")
    print()
    print("Unapproved ignores:")
    for item in unapproved:
        code_label = item.code if item.code is not None else "unscoped"
        print(f"  - {item.path}:{item.line_number} [{code_label}]")
        print(f"      {item.line_text.strip()}")
    print()


def _print_stale(stale: list[AllowlistEntry]) -> None:
    if not stale:
        return
    print(f"{YELLOW}⚠️  Stale allowlist entries detected.{NC}")
    print()
    print("These approvals no longer match live code and should be removed:")
    for entry in stale:
        code_label = entry.code if entry.code is not None else "unscoped"
        print(f"  - {entry.path} [{code_label}]")
        print(f"      match: {entry.match}")
    print()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ci", action="store_true", help="Exit non-zero on violations")
    args = parser.parse_args(argv)

    _print_header()

    ignores = _find_ignores()
    entries = _load_allowlist()

    matched_keys: set[tuple[str, str | None, str]] = set()
    unapproved: list[IgnoreUse] = []
    for ignore_use in ignores:
        entry = _match_entry(ignore_use, entries)
        if entry is None:
            unapproved.append(ignore_use)
            continue
        matched_keys.add(entry.key)

    stale = [entry for entry in entries if entry.key not in matched_keys]

    _print_results(ignores, entries, unapproved, stale)
    _print_unapproved(unapproved)
    _print_stale(stale)

    if not unapproved and not stale:
        print(f"{GREEN}✅ Production # type: ignore allowlist OK{NC}")
        print()
        print(f"Allowlist file: {_allowlist_path().relative_to(_repo_root())}")
        return 0

    if args.ci:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
