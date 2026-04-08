#!/usr/bin/env python3
"""Generate committed codebase metrics history for local development."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List


class CodebaseAnalyzer:
    """Analyze the repository and build a lightweight history entry."""

    EXCLUDE_DIRS = {
        "venv",
        "env",
        ".venv",
        "node_modules",
        ".next",
        "dist",
        "build",
        "out",
        "__pycache__",
        ".pytest_cache",
        ".git",
        ".github",
        "coverage",
        ".coverage",
        ".mypy_cache",
        "htmlcov",
        ".idea",
        ".vscode",
        "migrations/versions",
        "logs",
        "*.egg-info",
    }
    AUTO_GENERATED_PATTERNS = {"frontend/types/generated"}
    BACKEND_EXTENSIONS = {".py"}
    FRONTEND_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}

    def __init__(self, root_path: str | None = None):
        self.root_path = self._resolve_root(root_path)
        self.backend_path = self.root_path / "backend"
        self.frontend_path = self.root_path / "frontend"

    @staticmethod
    def _resolve_root(root_path: str | None) -> Path:
        if root_path:
            return Path(root_path).resolve()

        current = Path.cwd().resolve()
        while current != current.parent:
            if (current / "backend").exists() and (current / "frontend").exists():
                return current
            current = current.parent

        script_path = Path(__file__).resolve()
        current = script_path.parent
        while current != current.parent:
            if (current / "backend").exists() and (current / "frontend").exists():
                return current
            current = current.parent

        return Path.cwd().resolve()

    def should_exclude(self, path: Path) -> bool:
        parts = path.parts
        for part in parts:
            if part in self.EXCLUDE_DIRS or part.startswith("."):
                return True
            if part.endswith(".egg-info"):
                return True
        posix_path = path.as_posix()
        return any(pattern in posix_path for pattern in self.AUTO_GENERATED_PATTERNS)

    def count_lines(self, file_path: Path) -> int:
        try:
            with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
                return sum(1 for line in handle if line.strip())
        except OSError:
            return 0

    def analyze_directory(
        self, directory: Path, extensions: set[str], category_mapping: Dict[str, List[str]] | None = None
    ) -> Dict[str, Any]:
        if not directory.exists():
            return {"total_files": 0, "total_lines": 0, "categories": {}}

        files_by_category: Dict[str, Dict[str, int]] = {}
        total_files = 0
        total_lines = 0

        for ext in extensions:
            for file_path in directory.rglob(f"*{ext}"):
                if self.should_exclude(file_path):
                    continue

                lines = self.count_lines(file_path)
                total_files += 1
                total_lines += lines

                if not category_mapping:
                    continue

                rel_path = str(file_path.relative_to(directory))
                for category, patterns in category_mapping.items():
                    if any(pattern in rel_path for pattern in patterns):
                        stats = files_by_category.setdefault(category, {"files": 0, "lines": 0})
                        stats["files"] += 1
                        stats["lines"] += lines
                        break

        return {
            "total_files": total_files,
            "total_lines": total_lines,
            "categories": files_by_category,
        }

    def analyze_backend(self) -> Dict[str, Any]:
        category_mapping = {
            "Models": ["models/"],
            "Services": ["services/"],
            "Routes/APIs": ["routes/"],
            "Repositories": ["repositories/"],
            "Schemas": ["schemas/"],
            "Core/Config": ["core/"],
            "Tasks/Celery": ["tasks/"],
            "Unit Tests": ["tests/unit/"],
            "Integration Tests": ["tests/integration/"],
            "Route Tests": ["tests/routes/"],
            "Scripts": ["scripts/"],
            "Alembic": ["alembic/"],
        }
        return self.analyze_directory(self.backend_path, self.BACKEND_EXTENSIONS, category_mapping)

    def analyze_frontend(self) -> Dict[str, Any]:
        category_mapping = {
            "Components": ["components/"],
            "Pages": ["app/"],
            "Hooks": ["hooks/"],
            "API/Lib": ["lib/"],
            "Types": ["types/"],
            "Utils": ["utils/"],
            "Features": ["features/"],
            "Unit Tests": ["__tests__/"],
            "E2E Tests": ["e2e/"],
            "Styles": ["styles/"],
            "Public": ["public/"],
        }
        return self.analyze_directory(self.frontend_path, self.FRONTEND_EXTENSIONS, category_mapping)

    def _run_git(self, args: List[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=self.root_path,
            check=False,
        )

    def get_git_stats(self) -> Dict[str, Any]:
        try:
            commits_str = self._run_git(["rev-list", "--count", "HEAD"]).stdout.strip()
            commits = int(commits_str) if commits_str else 0

            contributor_lines = self._run_git(
                ["log", "--max-count=10000", "--format=%aN", "--no-merges"]
            ).stdout.splitlines()
            contributors = {line.strip() for line in contributor_lines if line.strip()}

            first_commit_lines = self._run_git(
                ["log", "--all", "--max-count=10000", "--reverse", "--format=%ai"]
            ).stdout.splitlines()
            first_commit_date = first_commit_lines[0][:10] if first_commit_lines else None

            last_commit = self._run_git(["log", "--max-count=1", "--format=%ai"]).stdout.strip()
            branch = self._run_git(["branch", "--show-current"]).stdout.strip()

            return {
                "git_commits": commits,
                "unique_contributors": len(contributors),
                "first_commit_date": first_commit_date,
                "last_commit_date": last_commit[:10] if last_commit else None,
                "branch": branch or None,
            }
        except Exception:
            return {
                "git_commits": 0,
                "unique_contributors": None,
                "first_commit_date": None,
                "last_commit_date": None,
                "branch": None,
            }

    def build_entry(self) -> Dict[str, Any]:
        backend = self.analyze_backend()
        frontend = self.analyze_frontend()
        git_stats = self.get_git_stats()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_lines": backend["total_lines"] + frontend["total_lines"],
            "total_files": backend["total_files"] + frontend["total_files"],
            "backend_lines": backend["total_lines"],
            "frontend_lines": frontend["total_lines"],
            "git_commits": git_stats["git_commits"],
            "categories": {
                "backend": backend["categories"],
                "frontend": frontend["categories"],
            },
            "backend_files": backend["total_files"],
            "frontend_files": frontend["total_files"],
            "unique_contributors": git_stats["unique_contributors"],
            "first_commit_date": git_stats["first_commit_date"],
            "last_commit_date": git_stats["last_commit_date"],
            "branch": git_stats["branch"],
        }


def _history_file(root_path: Path) -> Path:
    return root_path / "metrics_history.json"


def _validate_timestamp(value: Any, source: str) -> None:
    if not isinstance(value, str):
        raise RuntimeError(f"{source} timestamp must be a string.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RuntimeError(f"{source} timestamp must be a valid ISO-8601 datetime.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError(f"{source} timestamp must include timezone info.")
    if parsed.utcoffset() != timedelta(0):
        raise RuntimeError(f"{source} timestamp must be UTC.")


def _backfill_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(entry)
    normalized.setdefault("categories", None)
    normalized.setdefault("backend_files", None)
    normalized.setdefault("frontend_files", None)
    normalized.setdefault("unique_contributors", None)
    normalized.setdefault("first_commit_date", None)
    normalized.setdefault("last_commit_date", None)
    normalized.setdefault("branch", None)
    return normalized


def _entries_match(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    left_cmp = dict(left)
    right_cmp = dict(right)
    left_cmp.pop("timestamp", None)
    right_cmp.pop("timestamp", None)
    return left_cmp == right_cmp


def _parse_history(raw: str, source: str) -> List[Dict[str, Any]]:
    loaded = json.loads(raw)
    if not isinstance(loaded, list):
        raise RuntimeError(f"{source} must contain a JSON array.")
    history: List[Dict[str, Any]] = []
    for index, entry in enumerate(loaded):
        if not isinstance(entry, dict):
            raise RuntimeError(f"{source} entry {index} must be an object.")
        normalized = _backfill_entry(entry)
        _validate_timestamp(normalized.get("timestamp"), f"{source} entry {index}")
        history.append(normalized)
    return history


def _load_existing_history(root_path: Path) -> List[Dict[str, Any]]:
    history_path = _history_file(root_path)

    if history_path.exists():
        raw_history = history_path.read_text(encoding="utf-8")
        if raw_history.strip():
            return _parse_history(raw_history, "metrics_history.json")

    git_history = subprocess.run(
        ["git", "show", "HEAD:metrics_history.json"],
        capture_output=True,
        text=True,
        cwd=root_path,
        check=False,
    )
    if git_history.returncode == 0 and git_history.stdout.strip():
        return _parse_history(git_history.stdout, "HEAD:metrics_history.json")

    return []


def _coerce_git_commits(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _ensure_monotonic_git_commits(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized_history: List[Dict[str, Any]] = []
    previous_commits = 0

    for entry in history:
        normalized_entry = _backfill_entry(entry)
        commits = _coerce_git_commits(normalized_entry.get("git_commits"))
        if commits < previous_commits:
            commits = previous_commits
        normalized_entry["git_commits"] = commits
        previous_commits = commits
        normalized_history.append(normalized_entry)

    return normalized_history


def build_history(root_path: Path) -> List[Dict[str, Any]]:
    history = _ensure_monotonic_git_commits(_load_existing_history(root_path))

    analyzer = CodebaseAnalyzer(str(root_path))
    current_entry = analyzer.build_entry()
    _validate_timestamp(current_entry.get("timestamp"), "generated entry")
    if history:
        current_entry["git_commits"] = max(
            _coerce_git_commits(current_entry.get("git_commits")),
            _coerce_git_commits(history[-1].get("git_commits")),
        )

    if history and _entries_match(history[-1], current_entry):
        return history[-1000:]

    history.append(current_entry)
    return history[-1000:]


def main() -> int:
    if len(sys.argv) > 1:
        print(
            "backend/scripts/codebase_metrics.py no longer accepts arguments. "
            "Run `python backend/scripts/codebase_metrics.py > metrics_history.json`.",
            file=sys.stderr,
        )
        return 2

    try:
        repo_root = CodebaseAnalyzer().root_path
        history = build_history(repo_root)
    except Exception as exc:
        print(f"Failed to generate codebase metrics: {exc}", file=sys.stderr)
        return 1

    json.dump(history, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
