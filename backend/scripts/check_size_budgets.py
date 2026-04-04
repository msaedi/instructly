#!/usr/bin/env python3
"""Warn and fail on oversized backend/app files and functions."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SCOPE_ROOT = REPO_ROOT / "backend/app"
BASELINE_PATH = REPO_ROOT / "backend/.size-budget-baseline.txt"

SOFT_FILE_LINES = 500
HARD_FILE_LINES = 700
SOFT_MEMBER_LINES = 100
HARD_MEMBER_LINES = 125


@dataclass(frozen=True)
class MemberMetric:
    name: str
    lineno: int
    length: int


@dataclass(frozen=True)
class FileMetric:
    path: Path
    line_count: int
    soft_members: tuple[MemberMetric, ...]
    hard_members: tuple[MemberMetric, ...]

    @property
    def has_soft_file_violation(self) -> bool:
        return self.line_count > SOFT_FILE_LINES

    @property
    def has_hard_file_violation(self) -> bool:
        return self.line_count > HARD_FILE_LINES

    @property
    def has_soft_violation(self) -> bool:
        return self.has_soft_file_violation or bool(self.soft_members)

    @property
    def has_hard_violation(self) -> bool:
        return self.has_hard_file_violation or bool(self.hard_members)


def _repo_relative(path: Path) -> Path:
    resolved = path if path.is_absolute() else (REPO_ROOT / path)
    return resolved.resolve(strict=False).relative_to(REPO_ROOT)


def _is_in_scope(path: Path) -> bool:
    try:
        resolved = (path if path.is_absolute() else REPO_ROOT / path).resolve(strict=False)
    except OSError:
        return False
    return resolved == SCOPE_ROOT or SCOPE_ROOT in resolved.parents


def _iter_scope_files() -> list[Path]:
    if not SCOPE_ROOT.exists():
        return []
    return sorted(SCOPE_ROOT.rglob("*.py"))


def collect_files_from_args(paths: list[str]) -> list[Path]:
    if not paths:
        return _iter_scope_files()
    seen: set[Path] = set()
    files: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.suffix != ".py" or not _is_in_scope(path):
            continue
        normalized = _repo_relative(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        candidate = REPO_ROOT / normalized
        if candidate.exists():
            files.append(candidate)
    return files


def _member_name(
    parent: ast.AST,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str:
    if isinstance(parent, ast.ClassDef):
        return f"{parent.name}.{node.name}"
    return node.name


def _iter_measured_members(tree: ast.AST) -> list[MemberMetric]:
    parent_map = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    members: list[MemberMetric] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        parent = parent_map.get(node)
        if not isinstance(parent, (ast.Module, ast.ClassDef)):
            continue
        if node.end_lineno is None:
            continue
        members.append(
            MemberMetric(
                name=_member_name(parent, node),
                lineno=node.lineno,
                length=node.end_lineno - node.lineno + 1,
            )
        )
    return members


def measure_file(path: Path) -> FileMetric:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    line_count = len(source.splitlines())
    members = _iter_measured_members(tree)
    soft_members = tuple(
        member for member in members if SOFT_MEMBER_LINES < member.length <= HARD_MEMBER_LINES
    )
    hard_members = tuple(member for member in members if member.length > HARD_MEMBER_LINES)
    return FileMetric(
        path=_repo_relative(path),
        line_count=line_count,
        soft_members=soft_members,
        hard_members=hard_members,
    )


def load_baseline() -> set[Path]:
    if not BASELINE_PATH.exists():
        return set()
    entries: set[Path] = set()
    for raw_line in BASELINE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        entries.add(Path(line))
    return entries


def generate_baseline() -> int:
    metrics = [measure_file(path) for path in _iter_scope_files()]
    hard_paths = sorted(metric.path for metric in metrics if metric.has_hard_violation)
    output = "\n".join(path.as_posix() for path in hard_paths)
    if output:
        output += "\n"
    BASELINE_PATH.write_text(output, encoding="utf-8")
    print(f"Wrote {len(hard_paths)} baseline entries to {BASELINE_PATH.relative_to(REPO_ROOT)}")
    return 0


def _format_file_violation(metric: FileMetric, limit: int, severity: str) -> str:
    return (
        f"{severity} {metric.path.as_posix()}: {metric.line_count} lines "
        f"(limit {limit})"
    )


def _format_member_violation(
    path: Path,
    member: MemberMetric,
    limit: int,
    severity: str,
) -> str:
    return (
        f"{severity} {path.as_posix()}:{member.lineno}: {member.name} is "
        f"{member.length} lines (limit {limit})"
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate-baseline", action="store_true")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)

    if args.generate_baseline:
        return generate_baseline()

    metrics = [measure_file(path) for path in collect_files_from_args(args.files)]
    baseline = load_baseline()

    warnings: list[str] = []
    failures: list[str] = []
    stale_baseline_entries: list[Path] = []

    for metric in metrics:
        is_baselined = metric.path in baseline
        if metric.has_soft_file_violation and not metric.has_hard_file_violation:
            warnings.append(_format_file_violation(metric, SOFT_FILE_LINES, "WARN"))
        for member in metric.soft_members:
            warnings.append(_format_member_violation(metric.path, member, SOFT_MEMBER_LINES, "WARN"))

        if metric.has_hard_violation:
            target = warnings if is_baselined else failures
            target.append(
                _format_file_violation(
                    metric,
                    HARD_FILE_LINES,
                    "WARN" if is_baselined else "ERROR",
                )
            ) if metric.has_hard_file_violation else None
            for member in metric.hard_members:
                target.append(
                    _format_member_violation(
                        metric.path,
                        member,
                        HARD_MEMBER_LINES,
                        "WARN" if is_baselined else "ERROR",
                    )
                )
            if is_baselined:
                warnings.append(
                    f"WARN {metric.path.as_posix()}: hard limit violation allowed by "
                    f"{BASELINE_PATH.relative_to(REPO_ROOT).as_posix()}"
                )
        elif metric.path in baseline:
            stale_baseline_entries.append(metric.path)

    if stale_baseline_entries:
        failures.append(
            "ERROR backend/.size-budget-baseline.txt: remove stale baseline entries: "
            + ", ".join(path.as_posix() for path in sorted(stale_baseline_entries))
        )

    if warnings:
        print("\n".join(warnings))
    if failures:
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
