"""Test inventory helper for tracking skipped tests."""
from __future__ import annotations

import json
import os
from pathlib import Path

_INVENTORY = {"collection_skips": [], "runtime_skips": []}


def record_collection_skip(path: str, reason: str):
    """Record a test file that was skipped at collection time."""
    _INVENTORY["collection_skips"].append({"path": str(path), "reason": reason})


def record_runtime_skip(nodeid: str, reason: str):
    """Record a test that was skipped at runtime."""
    _INVENTORY["runtime_skips"].append({"nodeid": nodeid, "reason": reason})


def dump_inventory(dest: str | None = None):
    """Write inventory to JSON file."""
    out = dest or os.getenv("TEST_INVENTORY_OUT") or "TEST_INVENTORY.json"
    Path(out).write_text(json.dumps(_INVENTORY, indent=2), encoding="utf-8")
