#!/usr/bin/env python3
"""Toggle a local AlwaysFiring Prometheus alert for Slack smoke tests."""

from __future__ import annotations

import argparse
import datetime as _dt
import pathlib
import re
import sys
from typing import Final, List, Dict, Any

import yaml

ALERTS_PATH: Final[pathlib.Path] = pathlib.Path("monitoring/prometheus/alerts.yml")
TEST_GROUP_NAME: Final[str] = "test_local_alerts"
TEST_RULE: Final[Dict[str, Any]] = {
    "alert": "AlwaysFiring",
    "expr": "vector(1)",
    "for": "30s",
    "annotations": {
        "summary": "Test alert (local)",
        "description": "Manual smoke test to verify Slack wiring",
    },
}
TEST_GROUP: Final[Dict[str, Any]] = {
    "name": TEST_GROUP_NAME,
    "rules": [TEST_RULE],
}
GROUPS_REGEX: Final[re.Pattern[str]] = re.compile(r"^groups:\s*$", re.MULTILINE)


class MergingLoader(yaml.SafeLoader):
    """YAML loader that merges duplicate `groups` keys by concatenating lists."""


def _construct_mapping(loader: MergingLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        value = loader.construct_object(value_node, deep=deep)
        if key == "groups" and key in mapping:
            existing = mapping[key]
            if isinstance(existing, list) and isinstance(value, list):
                existing.extend(value)
            else:
                mapping[key] = value
        else:
            mapping[key] = value
    return mapping


MergingLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def _timestamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d%H%M%S")


def _make_backup(path: pathlib.Path) -> pathlib.Path:
    backup_path = path.with_name(f"{path.name}.bak.{_timestamp()}")
    backup_path.write_text(path.read_text())
    return backup_path


def _load_alerts(raw: str) -> Dict[str, Any]:
    data = yaml.load(raw, Loader=MergingLoader)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise SystemExit("alerts.yml must be a mapping with a top-level groups list")
    groups = data.get("groups")
    if groups is None:
        groups = []
        data["groups"] = groups
    if not isinstance(groups, list):
        raise SystemExit("alerts.yml `groups` key must be a list")
    # Ensure nested structures are dictionaries/lists as expected
    normalized_groups: List[Dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            raise SystemExit("Each group entry must be a mapping")
        name = group.get("name")
        rules = group.get("rules")
        if name is None or not isinstance(name, str):
            raise SystemExit("Each group must have a string `name`")
        if rules is None:
            rules = []
            group["rules"] = rules
        if not isinstance(rules, list):
            raise SystemExit("Group `rules` must be a list")
        normalized_groups.append(group)
    data["groups"] = normalized_groups
    return data


def _write_alerts(data: Dict[str, Any]) -> None:
    ALERTS_PATH.write_text(
        yaml.safe_dump(data, sort_keys=False, indent=2, default_flow_style=False)
    )


def _validate_yaml(path: pathlib.Path, backup_path: pathlib.Path | None) -> None:
    try:
        yaml.safe_load(path.read_text())
    except Exception as exc:  # pragma: no cover - defensive
        if backup_path is not None:
            path.write_text(backup_path.read_text())
        print(f"YAML validation failed: {exc}", file=sys.stderr)
        sys.exit(1)


def toggle(mode: str) -> None:
    if not ALERTS_PATH.exists():
        print(f"alerts file not found at {ALERTS_PATH}", file=sys.stderr)
        sys.exit(1)

    raw = ALERTS_PATH.read_text()
    duplicate_groups = len(GROUPS_REGEX.findall(raw)) > 1
    data = _load_alerts(raw)
    groups: List[Dict[str, Any]] = data["groups"]

    def _find_group_index(name: str) -> int | None:
        for idx, group in enumerate(groups):
            if group.get("name") == name:
                return idx
        return None

    backup_path: pathlib.Path | None = None

    if mode == "on":
        exists = _find_group_index(TEST_GROUP_NAME) is not None
        if not exists or duplicate_groups:
            backup_path = _make_backup(ALERTS_PATH)
            if not exists:
                groups.append(TEST_GROUP)
            data["groups"] = groups
            _write_alerts(data)
            _validate_yaml(ALERTS_PATH, backup_path)
            if not exists:
                print("Added test alert.")
            else:
                print("Normalized alerts file (test alert already present).")
        else:
            print("Test alert already present; nothing to do.")

    elif mode == "off":
        index = _find_group_index(TEST_GROUP_NAME)
        if index is not None or duplicate_groups:
            backup_path = _make_backup(ALERTS_PATH)
            if index is not None:
                groups.pop(index)
            data["groups"] = groups
            _write_alerts(data)
            _validate_yaml(ALERTS_PATH, backup_path)
            if index is not None:
                print("Removed test alert.")
            else:
                print("Normalized alerts file.")
        else:
            print("Test alert already removed; nothing to do.")
    else:  # pragma: no cover - argparse guards
        raise ValueError(f"Unknown mode: {mode}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("on", "off"), help="Turn the test alert on or off")
    args = parser.parse_args(argv)
    toggle(args.mode)


if __name__ == "__main__":  # pragma: no cover
    main()
