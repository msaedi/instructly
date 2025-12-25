#!/usr/bin/env python3
"""
Check backend code for naive datetime usage.

Blocked patterns:
- datetime.now()
- datetime.combine(date, time) without tzinfo
- date.today()

Allowed patterns:
- datetime.now(timezone.utc)
- datetime.now(tz=timezone.utc)
- datetime.combine(date, time, tzinfo=timezone.utc)

Exception marker (line or immediately above):
    # utc-naive-ok: Display to user in local timezone
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
import os
import sys
from typing import Iterable, List, Sequence

MARKER = "utc-naive-ok: Display to user in local timezone"
DEFAULT_ROOT = os.path.join("backend", "app")


@dataclass(frozen=True)
class Violation:
    filename: str
    line: int
    message: str
    code: str


def _collect_py_files(targets: Sequence[str]) -> List[str]:
    files: set[str] = set()
    for target in targets:
        if os.path.isdir(target):
            for root, _, filenames in os.walk(target):
                for name in filenames:
                    if name.endswith(".py"):
                        files.add(os.path.join(root, name))
        elif target.endswith(".py") and os.path.isfile(target):
            files.add(target)
    return sorted(files)


def _build_ignored_lines(lines: Sequence[str]) -> set[int]:
    ignored: set[int] = set()
    for idx, line in enumerate(lines, start=1):
        if MARKER in line:
            ignored.add(idx)
            if idx + 1 <= len(lines):
                ignored.add(idx + 1)
    return ignored


def _is_name_attr(node: ast.AST, name: str, attr: str) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == name
        and node.attr == attr
    )


class _Visitor(ast.NodeVisitor):
    def __init__(self, filename: str, lines: Sequence[str], ignored: set[int]) -> None:
        self._filename = filename
        self._lines = lines
        self._ignored = ignored
        self.violations: List[Violation] = []

    def _record(self, node: ast.AST, message: str) -> None:
        lineno = getattr(node, "lineno", None)
        if not lineno:
            return
        if lineno in self._ignored:
            return
        code = self._lines[lineno - 1].rstrip()
        self.violations.append(
            Violation(
                filename=self._filename,
                line=lineno,
                message=message,
                code=code,
            )
        )

    def visit_Call(self, node: ast.Call) -> None:
        if _is_name_attr(node.func, "datetime", "now"):
            if not node.args and not node.keywords:
                self._record(node, "Use datetime.now(timezone.utc) or datetime.now(tz=timezone.utc)")
        elif _is_name_attr(node.func, "date", "today"):
            if not node.args and not node.keywords:
                self._record(node, "Use datetime.now(timezone.utc).date() instead of date.today()")
        elif _is_name_attr(node.func, "datetime", "combine"):
            has_tzinfo_kw = any(
                kw.arg == "tzinfo" for kw in node.keywords if isinstance(kw, ast.keyword)
            )
            has_third_arg = len(node.args) >= 3
            if not has_tzinfo_kw and not has_third_arg:
                self._record(
                    node,
                    "Use datetime.combine(..., tzinfo=timezone.utc) or pass a tzinfo argument",
                )

        self.generic_visit(node)


def _scan_file(path: str) -> List[Violation]:
    with open(path, "r", encoding="utf-8") as handle:
        content = handle.read()
    lines = content.splitlines()
    ignored = _build_ignored_lines(lines)

    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError:
        return []

    visitor = _Visitor(path, lines, ignored)
    visitor.visit(tree)
    return visitor.violations


def _scan_files(paths: Iterable[str]) -> List[Violation]:
    violations: List[Violation] = []
    for path in paths:
        violations.extend(_scan_file(path))
    return violations


def main(argv: Sequence[str]) -> int:
    targets = list(argv)
    if not targets:
        targets = [DEFAULT_ROOT]

    files = _collect_py_files(targets)
    violations = _scan_files(files)

    if not violations:
        return 0

    print("UTC timezone enforcement failed.")
    for violation in violations:
        print(
            f"{violation.filename}:{violation.line}: {violation.message}\n"
            f"  {violation.code}"
        )
    print(f"Found {len(violations)} violation(s).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
