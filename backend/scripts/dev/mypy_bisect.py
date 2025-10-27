#!/usr/bin/env python3
"""
Utility to pinpoint the smallest set of files that causes mypy to crash.

This is intended for diagnosing internal mypy errors on selected parts of the
codebase without touching business logic.
"""

from __future__ import annotations

import argparse
import itertools
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Iterable, Sequence

DEFAULT_TARGETS = [
    "app/core",
    "app/models",
    "app/notifications",
    "app/repositories",
    "app/routes",
    "app/services",
    "app/tasks",
    "app/templates",
    "app/utils",
]


REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / ".mypy_cache_bisect"
LOG_DIR = REPO_ROOT / ".mypy_bisect_logs"
CRASH_TOKEN = "Internal error: unresolved placeholder type None"


class MypyRunner:
    """Executes mypy with sanitized environment and caches results per subset."""

    def __init__(self) -> None:
        LOG_DIR.mkdir(exist_ok=True)
        self._attempt = 0
        self._memo: dict[tuple[str, ...], bool] = {}

    def run(self, paths: Sequence[str]) -> bool:
        """Run mypy for the given relative paths. Returns True on success."""
        key = tuple(paths)
        if not key:
            return True
        if key in self._memo:
            return self._memo[key]

        self._attempt += 1
        if CACHE_DIR.exists():
            shutil.rmtree(CACHE_DIR)

        env = os.environ.copy()
        env.pop("MYPYPATH", None)
        env.pop("PYTHONPATH", None)

        cmd = [
            "./venv/bin/mypy",
            "--no-incremental",
            "--cache-dir",
            str(CACHE_DIR),
            *key,
        ]
        proc = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        log_content = "$ " + " ".join(cmd) + "\n\n" + proc.stdout
        log_file = LOG_DIR / f"attempt_{self._attempt:04d}.log"
        log_file.write_text(log_content)
        (LOG_DIR / "last.txt").write_text(log_content)

        crashed = CRASH_TOKEN in proc.stdout
        success = not crashed
        if proc.returncode != 0 and not crashed:
            print(
                f"[warn] mypy exited with {proc.returncode} but did not crash; "
                f"see {log_file}",
                file=sys.stderr,
            )

        self._memo[key] = success
        return success


def resolve_targets(raw_targets: Sequence[str]) -> list[Path]:
    """Resolve provided targets relative to the repo root."""
    resolved: list[Path] = []
    for target in raw_targets:
        path = Path(target)
        if not path.is_absolute():
            path = (REPO_ROOT / target).resolve()
        else:
            path = path.resolve()
        if not path.exists():
            print(f"[warn] target not found: {target}", file=sys.stderr)
            continue
        resolved.append(path)
    return resolved


def iter_py_files(paths: Iterable[Path]) -> Iterable[Path]:
    """Yield python files under the provided directories/files."""
    for path in paths:
        if "__pycache__" in path.parts:
            continue
        if path.is_file() and path.suffix == ".py":
            yield path
            continue
        if path.is_dir():
            for child in path.rglob("*.py"):
                if "__pycache__" in child.parts:
                    continue
                yield child


def unique_relative_files(files: Iterable[Path]) -> list[str]:
    """Return sorted unique relative paths with original ordering preserved."""
    seen: set[str] = set()
    ordered: list[str] = []
    for path in files:
        rel = os.path.relpath(path, REPO_ROOT)
        if rel not in seen:
            seen.add(rel)
            ordered.append(rel)
    return ordered


def split_sequence(sequence: Sequence[str], parts: int) -> list[list[str]]:
    """Split sequence into `parts` contiguous chunks."""
    length = len(sequence)
    if parts <= 0 or length == 0:
        return []
    chunk_size = length // parts
    remainder = length % parts
    result: list[list[str]] = []
    start = 0
    for i in range(parts):
        extra = 1 if i < remainder else 0
        end = start + chunk_size + extra
        if start >= length:
            break
        chunk = list(sequence[start:end])
        if chunk:
            result.append(chunk)
        start = end
    return result


def complement(sequence: Sequence[str], subset: Sequence[str]) -> list[str]:
    subset_set = set(subset)
    return [item for item in sequence if item not in subset_set]


def ddmin(sequence: Sequence[str], tester: MypyRunner) -> list[str]:
    """
    Delta-debugging reduction to find a minimal failing subset.

    Returns a subset for which tester.run returns False, and removing any
    further chunk (according to the algorithm) would make the failure disappear.
    """
    current = list(sequence)
    n = 2
    while len(current) >= 2:
        subsets = split_sequence(current, n)
        if not subsets or len(subsets[0]) == len(current):
            break
        reduced = False

        for subset in subsets:
            if not tester.run(subset):
                current = subset
                n = 2
                reduced = True
                break
        if reduced:
            continue

        for subset in subsets:
            complement_set = complement(current, subset)
            if complement_set and not tester.run(complement_set):
                current = complement_set
                n = max(n - 1, 2)
                reduced = True
                break
        if not reduced:
            if n >= len(current):
                break
            n = min(len(current), n * 2)
    return current


def find_small_combo(
    candidates: Sequence[str],
    tester: MypyRunner,
    max_k: int = 3,
) -> list[str]:
    """Try to find failing combos up to size max_k."""
    count = len(candidates)
    upper = min(max_k, count)
    for size in range(1, upper + 1):
        for combo in itertools.combinations(candidates, size):
            if not tester.run(list(combo)):
                return list(combo)
    return list(candidates)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bisect mypy crashes down to the smallest file set."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=DEFAULT_TARGETS,
        help="Files or directories to inspect (default covers known crash areas).",
    )
    parser.add_argument(
        "--max-combo",
        type=int,
        default=3,
        help="Maximum combination size to search exhaustively (default: 3).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    resolved = resolve_targets(args.paths)
    files = unique_relative_files(iter_py_files(resolved))
    if not files:
        print("No Python files found under provided targets.", file=sys.stderr)
        sys.exit(2)

    runner = MypyRunner()
    print(f"[info] Testing {len(files)} files...")
    if runner.run(files):
        print("[info] Provided files do not reproduce the crash.")
        sys.exit(0)

    reduced = ddmin(files, runner)
    minimal = find_small_combo(reduced, runner, max_k=args.max_combo)

    if len(minimal) == 1:
        print(f"CRASH FILE: {minimal[0]}")
    else:
        print("CRASH SET:", " ".join(minimal))


if __name__ == "__main__":
    main()
