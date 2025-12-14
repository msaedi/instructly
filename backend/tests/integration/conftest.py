"""Selective gating: skip slot-era tests and expensive nightly tests at collection time."""
import os

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

# Check if nightly schemathesis tests should run
_RUN_NIGHTLY_SCHEMATHESIS = os.environ.get("RUN_NIGHTLY_SCHEMATHESIS", "0") == "1"


def pytest_ignore_collect(collection_path: Path, config):
    """Ignore slot-era test files and expensive nightly tests at collection time."""
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

    # Skip schemathesis tests unless RUN_NIGHTLY_SCHEMATHESIS=1
    # These tests take ~50s just to collect (schema loading from ASGI app)
    if "schemathesis" in p_obj.name and not _RUN_NIGHTLY_SCHEMATHESIS:
        record_collection_skip(p, "schemathesis (nightly-only, set RUN_NIGHTLY_SCHEMATHESIS=1)")
        return True

    # Return True (ignore) if slot-era, False (collect) otherwise
    if is_slot_era_file(p):
        record_collection_skip(p, "slot-era (AST) in integration (top-level)")
        return True  # Ignore slot-era files
    return False  # Collect safe files
