#!/usr/bin/env python3
"""
Codebase Metrics Analyzer for InstaInstru
Provides detailed statistics about the codebase size and composition.
Excludes all auto-generated and dependency files.
"""

from datetime import datetime
import json
from pathlib import Path
import subprocess
from typing import Dict, List


class CodebaseAnalyzer:
    """Analyzes codebase metrics excluding auto-generated files."""

    # Directories to exclude (auto-generated or dependencies)
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
        "migrations/versions",  # Alembic auto-generated
        ".DS_Store",
        "logs",
        "*.egg-info",
    }

    # Auto-generated paths that should never count toward metrics (e.g. OpenAPI d.ts)
    AUTO_GENERATED_PATTERNS = {
        "frontend/types/generated",
    }

    # File extensions to analyze
    BACKEND_EXTENSIONS = {".py"}
    FRONTEND_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}
    CONFIG_EXTENSIONS = {".json", ".yaml", ".yml", ".toml", ".env.example"}
    DOC_EXTENSIONS = {".md", ".rst", ".txt"}

    def __init__(self, root_path: str = None):
        # Auto-detect project root by looking for backend and frontend directories
        if root_path:
            self.root_path = Path(root_path).resolve()
        else:
            # Start from script location if called directly, or cwd if imported
            script_path = Path(__file__).resolve()

            # Always start from the script's location and go up to find project root
            current = script_path.parent
            while current != current.parent:
                if (current / "backend").exists() and (current / "frontend").exists():
                    self.root_path = current
                    break
                current = current.parent
            else:
                # If still not found, try from current working directory
                current = Path.cwd()
                while current != current.parent:
                    if (current / "backend").exists() and (current / "frontend").exists():
                        self.root_path = current
                        break
                    current = current.parent
                else:
                    # Last resort: assume project structure
                    self.root_path = Path.cwd()

        self.backend_path = self.root_path / "backend"
        self.frontend_path = self.root_path / "frontend"

        # Verify paths exist
        if not self.backend_path.exists() or not self.frontend_path.exists():
            print("⚠️  Warning: Could not find backend or frontend directories")
            print(f"   Searching from: {self.root_path}")
            print(f"   Backend path: {self.backend_path} (exists: {self.backend_path.exists()})")
            print(f"   Frontend path: {self.frontend_path} (exists: {self.frontend_path.exists()})")
            print("   Try running from project root or use --path option")

    def should_exclude(self, path: Path) -> bool:
        """Check if a path should be excluded."""
        parts = path.parts
        for part in parts:
            if part in self.EXCLUDE_DIRS or part.startswith("."):
                return True
            if part.endswith(".egg-info"):
                return True
        posix_path = path.as_posix()
        for pattern in self.AUTO_GENERATED_PATTERNS:
            if pattern in posix_path:
                return True
        return False

    def count_lines(self, file_path: Path) -> int:
        """Count non-empty lines in a file."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return sum(1 for line in f if line.strip())
        except:
            return 0

    def analyze_directory(
        self, directory: Path, extensions: set, category_mapping: Dict[str, List[str]] = None
    ) -> Dict:
        """Analyze a directory and return metrics."""
        if not directory.exists():
            return {
                "total_files": 0,
                "total_lines": 0,
                "total_lines_with_blanks": 0,
                "categories": {},
                "largest_files": [],
            }

        files_by_category = {}
        all_files = []
        total_lines = 0
        total_lines_with_blanks = 0

        for ext in extensions:
            for file_path in directory.rglob(f"*{ext}"):
                if self.should_exclude(file_path):
                    continue

                # Count lines
                lines = self.count_lines(file_path)
                total_lines += lines

                # Count with blanks
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines_with_blanks = sum(1 for _ in f)
                    total_lines_with_blanks += lines_with_blanks
                except:
                    lines_with_blanks = lines
                    total_lines_with_blanks += lines

                # Store file info
                rel_path = file_path.relative_to(directory)
                file_info = {
                    "path": str(rel_path),
                    "lines": lines,
                    "lines_with_blanks": lines_with_blanks,
                    "size_kb": file_path.stat().st_size / 1024,
                }
                all_files.append(file_info)

                # Categorize
                if category_mapping:
                    for category, patterns in category_mapping.items():
                        for pattern in patterns:
                            if pattern in str(rel_path):
                                if category not in files_by_category:
                                    files_by_category[category] = {"files": 0, "lines": 0}
                                files_by_category[category]["files"] += 1
                                files_by_category[category]["lines"] += lines
                                break

        # Get largest files
        largest_files = sorted(all_files, key=lambda x: x["lines"], reverse=True)[:10]

        return {
            "total_files": len(all_files),
            "total_lines": total_lines,
            "total_lines_with_blanks": total_lines_with_blanks,
            "categories": files_by_category,
            "largest_files": largest_files,
        }

    def analyze_backend(self) -> Dict:
        """Analyze backend Python code."""
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

    def analyze_frontend(self) -> Dict:
        """Analyze frontend TypeScript/JavaScript code."""
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

    def get_git_stats(self) -> Dict:
        """Get git repository statistics."""
        try:
            # Get total commits
            commits_str = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"], capture_output=True, text=True, cwd=self.root_path
            ).stdout.strip()
            commits = int(commits_str) if commits_str else 0

            # Prefer the highest value between Git and persisted history (handles shallow clones)
            history_commits = 0
            history_file = self.root_path / "metrics_history.json"
            if history_file.exists():
                try:
                    with open(history_file, "r") as f:
                        history = json.load(f)
                    if history:
                        history_commits = int(history[-1].get("git_commits", 0) or 0)
                except Exception:
                    history_commits = 0
            commits = max(commits, history_commits)

            # Get contributors
            contributors = (
                subprocess.run(
                    ["git", "log", "--format=%aN", "--no-merges"], capture_output=True, text=True, cwd=self.root_path
                )
                .stdout.strip()
                .split("\n")
            )
            unique_contributors = len(set(contributors))

            # Get first and last commit dates
            # Note: --reverse with --max-count has issues, so we use head/tail instead
            all_commits = (
                subprocess.run(
                    ["git", "log", "--all", "--reverse", "--format=%ai"],
                    capture_output=True,
                    text=True,
                    cwd=self.root_path,
                )
                .stdout.strip()
                .split("\n")
            )

            first_commit = all_commits[0] if all_commits else ""

            # Get the most recent commit
            last_commit = subprocess.run(
                ["git", "log", "-1", "--format=%ai"], capture_output=True, text=True, cwd=self.root_path
            ).stdout.strip()

            # Get current branch
            branch = subprocess.run(
                ["git", "branch", "--show-current"], capture_output=True, text=True, cwd=self.root_path
            ).stdout.strip()

            return {
                "total_commits": commits,
                "unique_contributors": unique_contributors,
                "first_commit": first_commit[:10] if first_commit else "N/A",
                "last_commit": last_commit[:10] if last_commit else "N/A",
                "current_branch": branch or "N/A",
            }
        except:
            return {
                "total_commits": 0,
                "unique_contributors": 0,
                "first_commit": "N/A",
                "last_commit": "N/A",
                "current_branch": "N/A",
            }

    def format_number(self, num: int) -> str:
        """Format number with thousands separator."""
        return f"{num:,}"

    def generate_report(self) -> str:
        """Generate a comprehensive metrics report."""
        print("🔍 Analyzing codebase...")

        backend = self.analyze_backend()
        frontend = self.analyze_frontend()
        git_stats = self.get_git_stats()

        # Calculate totals
        total_files = backend["total_files"] + frontend["total_files"]
        total_lines = backend["total_lines"] + frontend["total_lines"]

        # Calculate ratios
        backend_pct = (backend["total_lines"] / total_lines * 100) if total_lines > 0 else 0
        frontend_pct = (frontend["total_lines"] / total_lines * 100) if total_lines > 0 else 0

        # Test coverage ratio
        backend_test_lines = sum(
            backend["categories"].get(cat, {}).get("lines", 0)
            for cat in ["Unit Tests", "Integration Tests", "Route Tests"]
        )
        backend_app_lines = (
            backend["total_lines"] - backend_test_lines - backend["categories"].get("Scripts", {}).get("lines", 0)
        )

        frontend_test_lines = sum(
            frontend["categories"].get(cat, {}).get("lines", 0) for cat in ["Unit Tests", "E2E Tests"]
        )
        frontend_app_lines = frontend["total_lines"] - frontend_test_lines

        test_ratio_backend = (backend_test_lines / backend_app_lines * 100) if backend_app_lines > 0 else 0
        test_ratio_frontend = (frontend_test_lines / frontend_app_lines * 100) if frontend_app_lines > 0 else 0

        # Build report
        report = []
        report.append("=" * 80)
        report.append("📊 INSTAINSTRU CODEBASE METRICS REPORT")
        report.append("=" * 80)
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")

        # Executive Summary
        report.append("📈 EXECUTIVE SUMMARY")
        report.append("-" * 40)
        report.append(f"Total Lines of Code:    {self.format_number(total_lines)}")
        report.append(f"Total Files:            {self.format_number(total_files)}")
        report.append(f"Language Distribution:  Python {backend_pct:.1f}% | TypeScript/JS {frontend_pct:.1f}%")
        report.append(
            f"Test Coverage Ratio:    Backend {test_ratio_backend:.1f}% | Frontend {test_ratio_frontend:.1f}%"
        )
        report.append("")

        # Git Statistics
        if git_stats["total_commits"] > 0:
            report.append("📝 GIT STATISTICS")
            report.append("-" * 40)
            report.append(f"Total Commits:          {self.format_number(git_stats['total_commits'])}")
            report.append(f"Contributors:           {git_stats['unique_contributors']}")
            report.append(f"First Commit:           {git_stats['first_commit']}")
            report.append(f"Last Commit:            {git_stats['last_commit']}")
            report.append(f"Current Branch:         {git_stats['current_branch']}")
            report.append("")

        # Backend Details
        report.append("🐍 BACKEND (Python/FastAPI)")
        report.append("-" * 40)
        report.append(f"Total Files:            {self.format_number(backend['total_files'])}")
        report.append(f"Total Lines:            {self.format_number(backend['total_lines'])}")
        report.append(
            f"Average File Size:      {backend['total_lines'] // backend['total_files'] if backend['total_files'] > 0 else 0} lines"
        )
        report.append("")

        if backend["categories"]:
            report.append("Category Breakdown:")
            for category in sorted(backend["categories"].keys()):
                stats = backend["categories"][category]
                report.append(
                    f"  {category:20} {stats['files']:4} files | {self.format_number(stats['lines']):>10} lines"
                )
        report.append("")

        # Frontend Details
        report.append("⚛️  FRONTEND (TypeScript/Next.js)")
        report.append("-" * 40)
        report.append(f"Total Files:            {self.format_number(frontend['total_files'])}")
        report.append(f"Total Lines:            {self.format_number(frontend['total_lines'])}")
        report.append(
            f"Average File Size:      {frontend['total_lines'] // frontend['total_files'] if frontend['total_files'] > 0 else 0} lines"
        )
        report.append("")

        if frontend["categories"]:
            report.append("Category Breakdown:")
            for category in sorted(frontend["categories"].keys()):
                stats = frontend["categories"][category]
                report.append(
                    f"  {category:20} {stats['files']:4} files | {self.format_number(stats['lines']):>10} lines"
                )
        report.append("")

        # Largest Files
        report.append("📁 LARGEST FILES (Top 10)")
        report.append("-" * 40)

        all_large_files = []
        for file_info in backend["largest_files"]:
            file_info["section"] = "Backend"
            all_large_files.append(file_info)
        for file_info in frontend["largest_files"]:
            file_info["section"] = "Frontend"
            all_large_files.append(file_info)

        all_large_files.sort(key=lambda x: x["lines"], reverse=True)

        for i, file_info in enumerate(all_large_files[:10], 1):
            report.append(
                f"{i:2}. [{file_info['section']:8}] {file_info['path'][:50]:50} {self.format_number(file_info['lines']):>8} lines"
            )

        report.append("")
        report.append("=" * 80)
        report.append("Note: All dependency directories (venv, node_modules, etc.) are excluded")
        report.append("=" * 80)

        return "\n".join(report)

    def save_metrics_history(self):
        """Save metrics to a JSON file for tracking over time."""
        history_file = self.root_path / "metrics_history.json"

        backend = self.analyze_backend()
        frontend = self.analyze_frontend()
        git_stats = self.get_git_stats()

        metrics = {
            "timestamp": datetime.now().isoformat(),
            "total_lines": backend["total_lines"] + frontend["total_lines"],
            "total_files": backend["total_files"] + frontend["total_files"],
            "backend_lines": backend["total_lines"],
            "frontend_lines": frontend["total_lines"],
            "git_commits": git_stats["total_commits"],
            "categories": {"backend": backend["categories"], "frontend": frontend["categories"]},
        }

        # Load existing history
        history = []
        if history_file.exists():
            try:
                with open(history_file, "r") as f:
                    history = json.load(f)
            except:
                pass

        # Add new metrics (preserve monotonic git commit count)
        if history:
            prev_git = history[-1].get("git_commits", 0)
            if metrics["git_commits"] < prev_git:
                raise RuntimeError(
                    "Refusing to append codebase metrics: git commit total would decrease."
                    " Run the collector from a full clone or investigate the history file."
                )

        history.append(metrics)

        # Keep only last 100 entries
        history = history[-100:]

        # Save updated history
        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)

        print(f"✅ Metrics saved to {history_file}")

        # Show growth if we have history
        if len(history) > 1:
            prev = history[-2]
            growth = metrics["total_lines"] - prev["total_lines"]
            if growth != 0:
                print(f"📈 Growth since last run: {growth:+,} lines")


def main():
    """Run the codebase analyzer."""
    import argparse

    parser = argparse.ArgumentParser(description="Analyze iNSTAiNSTRU codebase metrics")
    parser.add_argument("--save", action="store_true", help="Save metrics to history file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--path", default=".", help="Root path of the project")

    args = parser.parse_args()

    analyzer = CodebaseAnalyzer(args.path)

    if args.json:
        # Output raw data as JSON
        backend = analyzer.analyze_backend()
        frontend = analyzer.analyze_frontend()
        git_stats = analyzer.get_git_stats()

        data = {
            "timestamp": datetime.now().isoformat(),
            "backend": backend,
            "frontend": frontend,
            "git": git_stats,
            "summary": {
                "total_lines": backend["total_lines"] + frontend["total_lines"],
                "total_files": backend["total_files"] + frontend["total_files"],
            },
        }
        print(json.dumps(data, indent=2))
    else:
        # Generate human-readable report
        report = analyzer.generate_report()
        print(report)

        if args.save:
            analyzer.save_metrics_history()


if __name__ == "__main__":
    main()
