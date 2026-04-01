from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_importing_prep_db_does_not_import_database_layer() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    script = """
import os
import sys

sys.path.insert(0, {backend_dir!r})
os.environ["DB_CONFIRM_BYPASS"] = "1"

import scripts.prep_db  # noqa: F401

assert "app.database" not in sys.modules
assert "scripts.seed_chat_fixture" not in sys.modules
print("ok")
""".format(backend_dir=str(backend_dir))

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"
