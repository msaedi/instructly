"""Selective gating: skip slot-era tests at collection time."""
# Fallback in case this file is run in isolation or a different rootdir is inferred
try:
    import backend  # noqa: F401
except ModuleNotFoundError:
    from pathlib import Path
    import sys

    _REPO_ROOT = Path(__file__).resolve().parents[3]  # <repo>/
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from pathlib import Path

from backend.tests._inventory import record_collection_skip
from backend.tests._slot_era_detector import is_slot_era_file


def pytest_ignore_collect(collection_path: Path, config):
    """Ignore slot-era test files at collection time."""
    p = str(collection_path)
    if "backend/tests/unit/services" not in p and not p.endswith("/backend/tests/unit/services"):
        return False

    if not p.endswith(".py"):
        return False

    # Return True (ignore) if slot-era, False (collect) otherwise
    if is_slot_era_file(p):
        record_collection_skip(p, "slot-era (AST) in unit/services")
        return True  # Ignore slot-era files
    return False  # Collect safe files
