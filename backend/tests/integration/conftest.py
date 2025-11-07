"""Selective gating: skip slot-era tests at collection time."""
# Fallback in case this file is run in isolation or a different rootdir is inferred
try:
    import backend  # noqa: F401
except ModuleNotFoundError:
    from pathlib import Path
    import sys

    _REPO_ROOT = Path(__file__).resolve().parents[2]  # <repo>/
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from pathlib import Path

from backend.tests._inventory import record_collection_skip
from backend.tests._slot_era_detector import is_slot_era_file


def pytest_ignore_collect(collection_path: Path, config):
    """Ignore slot-era test files at collection time."""
    p = str(collection_path)
    p_obj = collection_path

    # Only handle test files in integration directory
    if "backend/tests/integration" not in p and "tests/integration" not in p:
        return False

    # Skip already-handled subdirectories (they have their own conftest.py)
    path_parts = p.split("/")
    if "repository_patterns" in path_parts or "services" in path_parts:
        return False

    if not p_obj.name.endswith(".py") or p_obj.name == "conftest.py":
        return False

    # Return True (ignore) if slot-era, False (collect) otherwise
    if is_slot_era_file(p):
        record_collection_skip(p, "slot-era (AST) in integration (top-level)")
        return True  # Ignore slot-era files
    return False  # Collect safe files
