"""Helpers for loading codebase metrics without shelling out."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import runpy
from typing import Any, Dict


def collect_codebase_metrics(repo_root: Path) -> Dict[str, Any]:
    """Return codebase metrics payload matching scripts/codebase_metrics.py JSON output."""
    script_path = repo_root / "backend" / "scripts" / "codebase_metrics.py"
    if not script_path.exists():
        raise RuntimeError(f"Metrics script not found at {script_path}")

    module_vars = runpy.run_path(str(script_path))
    analyzer_cls = module_vars.get("CodebaseAnalyzer")
    if analyzer_cls is None:
        raise RuntimeError("CodebaseAnalyzer not found in metrics script")

    analyzer = analyzer_cls(str(repo_root))
    backend = analyzer.analyze_backend()
    frontend = analyzer.analyze_frontend()
    git_stats = analyzer.get_git_stats()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "backend": backend,
        "frontend": frontend,
        "git": git_stats,
        "summary": {
            "total_lines": backend["total_lines"] + frontend["total_lines"],
            "total_files": backend["total_files"] + frontend["total_files"],
        },
    }
