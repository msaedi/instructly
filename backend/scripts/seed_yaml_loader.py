from pathlib import Path
from typing import Any, Dict, List

import yaml


class SeedDataLoader:
    def __init__(self, seed_data_dir: str = "backend/scripts/seed_data"):
        self.seed_data_dir = Path(seed_data_dir)
        self.config = self._load_yaml("config.yaml")
        self.instructors = self._load_yaml("instructors.yaml")
        self.students = self._load_yaml("students.yaml")
        self.availability_patterns = self._load_yaml("availability_patterns.yaml")
        self.bookings = self._load_yaml("bookings.yaml")

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        filepath = self.seed_data_dir / filename
        if not filepath.exists():
            return {}
        with open(filepath, "r") as f:
            return yaml.safe_load(f) or {}

    def get_instructors(self) -> List[Dict[str, Any]]:
        return self.instructors.get("instructors", [])

    def get_students(self) -> List[Dict[str, Any]]:
        return self.students.get("students", [])

    def get_availability_pattern(self, pattern_name: str) -> Dict[str, Any]:
        patterns = self.availability_patterns.get("patterns", {})
        return patterns.get(pattern_name, {})

    def get_default_password(self) -> str:
        return self.config.get("settings", {}).get("default_password", "Test123")
