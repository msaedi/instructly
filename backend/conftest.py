# Ensure '<repo root>' is on sys.path so 'import backend.*' works
# even when pytest rootdir is 'backend/'.
from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent  # <repo>/
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
