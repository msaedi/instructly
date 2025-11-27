# Ensure '<repo root>' is on sys.path so 'import backend.*' works
# even when pytest rootdir is 'backend/'.
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent  # <repo>/
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Skip dev scripts that look like tests but require running services
collect_ignore_glob = [
    # Dev scripts that hit live HTTP endpoints / require manual env (fail without running API)
    "scripts/dev/test_*.py",
    # Ops/diagnostic harnesses that send real alerts or depend on prod credentials
    "scripts/test_*.py",
    "scripts/monitoring/test_*.py",
    # Legacy perf harnesses that start FastAPI apps or time long-running operations
    "tests/performance/test_*.py",
]
