#!/usr/bin/env python3
"""Bulk convert response schemas to StrictModel with exclusion support."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, List, Tuple

SCHEMAS_ROOT = Path("backend/app/schemas")
EXCLUDE_FILE = Path("tools/response_strict_exclude.txt")
STRICT_IMPORT = "from ._strict_base import StrictModel\n"
CONFIG_IMPORT_SNIPPET = "from pydantic import ConfigDict\n"

CLASS_DEF_RE = re.compile(r"^(?P<indent>\s*)class\s+(?P<name>[A-Za-z0-9_]+)\s*\((?P<bases>[^)]*)\):")
SKIP_SUFFIXES = ("Request", "Create", "Update", "Confirm", "Reset", "Verify")


def load_exclusions() -> set[Tuple[str, str]]:
    exclusions: set[Tuple[str, str]] = set()
    if EXCLUDE_FILE.exists():
        for raw in EXCLUDE_FILE.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            filename, cls = line.split(":", 1)
            exclusions.add((filename.strip(), cls.strip()))
    return exclusions


def ensure_import(lines: List[str], import_line: str, predicate: callable) -> None:
    if predicate():
        return
    insert_at = 0
    for idx, line in enumerate(lines):
        if line.startswith("from .") or line.startswith("import"):
            insert_at = idx + 1
    lines.insert(insert_at, import_line)


def update_imports(lines: List[str], need_strict: bool, need_config: bool) -> None:
    if need_strict:
        ensure_import(lines, STRICT_IMPORT, lambda: any("StrictModel" in line and "_strict_base" in line for line in lines))
    if need_config:
        for idx, line in enumerate(lines):
            if line.startswith("from pydantic import"):
                if "ConfigDict" not in line:
                    line = line.rstrip("\n")
                    if line.endswith(")"):
                        # avoid trailing comment; simple append
                        line = line.replace(")", ", ConfigDict)")
                    else:
                        line = line + ", ConfigDict"
                    lines[idx] = line + "\n"
                need_config = False
                break
        if need_config:
            ensure_import(lines, CONFIG_IMPORT_SNIPPET, lambda: any("ConfigDict" in l and "from pydantic import" in l for l in lines))


def should_skip(name: str) -> bool:
    return any(name.endswith(suffix) for suffix in SKIP_SUFFIXES)


def find_class_body_end(lines: List[str], start_index: int, indent: str) -> int:
    body_indent = indent + "    "
    idx = start_index + 1
    while idx < len(lines):
        line = lines[idx]
        if not line.strip():
            idx += 1
            continue
        if not line.startswith(body_indent):
            break
        idx += 1
    return idx


def process_file(path: Path, exclusions: set[Tuple[str, str]]) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    changed = False
    need_strict_import = False
    need_config_import = False

    idx = 0
    while idx < len(lines):
        match = CLASS_DEF_RE.match(lines[idx])
        if not match:
            idx += 1
            continue

        class_name = match.group("name")
        bases_raw = match.group("bases")
        indent = match.group("indent")
        key = (path.name, class_name)

        if not class_name.endswith("Response") or should_skip(class_name) or key in exclusions:
            idx += 1
            continue

        bases = [base.strip() for base in bases_raw.split(",") if base.strip()]
        already_strict = any("StrictModel" in base for base in bases)

        if not bases:
            idx += 1
            continue

        if not already_strict and any("BaseModel" in base for base in bases):
            new_bases = [base.replace("BaseModel", "StrictModel") for base in bases]
            new_line = CLASS_DEF_RE.sub(
                f"{indent}class {class_name}({', '.join(new_bases)}):",
                lines[idx],
                count=1,
            )
            lines[idx] = new_line
            need_strict_import = True
            changed = True
            already_strict = True

        body_end = find_class_body_end(lines, idx, indent)
        body_lines = lines[idx + 1 : body_end]
        has_model_config = any("model_config" in line for line in body_lines)

        if already_strict and not has_model_config:
            insertion = f"{indent}    model_config = ConfigDict(extra=\"forbid\", validate_assignment=True)\n"
            lines.insert(idx + 1, insertion)
            body_end += 1
            need_config_import = True
            changed = True
        idx = body_end

    if changed:
        update_imports(lines, need_strict_import, need_config_import)
        path.write_text("".join(lines), encoding="utf-8")
    return changed


def iter_schema_files() -> Iterable[Path]:
    for file in SCHEMAS_ROOT.rglob("*.py"):
        if file.name in {"__init__.py", "_strict_base.py"}:
            continue
        yield file


def main() -> None:
    parser = argparse.ArgumentParser(description="Codemod response schemas to StrictModel")
    parser.add_argument("--dry-run", action="store_true", help="Report files that would change")
    args = parser.parse_args()

    exclusions = load_exclusions()
    changed_files: List[Path] = []

    for file in iter_schema_files():
        changed = process_file(file, exclusions)
        if changed:
            changed_files.append(file)

    if args.dry_run:
        for path in changed_files:
            print(path)


if __name__ == "__main__":
    main()
