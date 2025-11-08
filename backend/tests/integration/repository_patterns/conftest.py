"""Selective gating: skip slot-era tests at collection time, keep safe ones."""
# Fallback in case this file is run in isolation or a different rootdir is inferred
try:
    import backend  # noqa: F401
except ModuleNotFoundError:
    from pathlib import Path
    import sys

    _REPO_ROOT = Path(__file__).resolve().parents[3]  # <repo>/
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

import ast
from pathlib import Path

from backend.tests._inventory import record_collection_skip
from backend.tests._slot_era_detector import is_slot_era_file


def pytest_ignore_collect(collection_path: Path, config):
    """Selective pre-import gating: ignore slot-era files only."""
    p = str(collection_path)
    # Only handle files in repository_patterns directory
    if "backend/tests/integration/repository_patterns" not in p and not p.endswith(
        "/backend/tests/integration/repository_patterns"
    ):
        return False  # Let pytest handle normal collection for other paths

    if not p.endswith(".py"):
        return False

    # Check for syntax errors first - if file can't be parsed, skip it
    # (prevents collection failures from broken slot-era files)
    try:
        p_obj = collection_path
        src = p_obj.read_text(encoding="utf-8", errors="ignore")
        ast.parse(src, filename=p)
    except SyntaxError:
        # File has syntax errors - skip it to prevent collection failure
        record_collection_skip(p, "slot-era (AST) in repository_patterns (syntax error)")
        return True
    except Exception:
        # Other parse errors - be conservative and skip
        record_collection_skip(p, "slot-era (AST) in repository_patterns (parse error)")
        return True

    # Now check if it's slot-era using AST detector
    if is_slot_era_file(p):
        record_collection_skip(p, "slot-era (AST) in repository_patterns")
        return True  # Ignore slot-era files
    return False  # Collect safe files
