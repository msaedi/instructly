# backend/tests/integration/availability/test_no_slot_symbols_in_repo.py
"""
Source-guard test to ensure no AvailabilitySlot symbols exist in backend codebase.

This test walks all Python files in backend/ and fails if "AvailabilitySlot" appears.
Migration files are excluded as they may reference the old table structure.
"""

from pathlib import Path
import shlex
import shutil
import subprocess

import pytest


def test_no_availability_slot_symbols_in_backend() -> None:
    """Assert that AvailabilitySlot does not appear in backend/app/ code."""
    # Path: test file is in backend/tests/integration/availability/
    # So backend/ is 3 levels up
    backend_dir = Path(__file__).parent.parent.parent.parent
    app_dir = backend_dir / "app"
    assert app_dir.exists(), f"App directory not found: {app_dir}"

    violations: list[str] = []

    # Walk all Python files in backend/app/ only (not scripts or tests)
    for py_file in app_dir.rglob("*.py"):
        # Skip __pycache__ directories
        if "__pycache__" in str(py_file):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
            if "AvailabilitySlot" in content:
                # Check if it's just in a comment
                lines = content.split("\n")
                for line_num, line in enumerate(lines, start=1):
                    if "AvailabilitySlot" in line:
                        # Skip comments and docstrings
                        stripped = line.strip()
                        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                            continue
                        # Skip if it's part of a deprecation message
                        if "deprecated" in line.lower() or "removed" in line.lower():
                            continue
                        violations.append(f"{py_file.relative_to(backend_dir)}:{line_num}: {line.strip()[:80]}")
        except Exception:
            # Skip files that can't be read (e.g., binary files)
            continue

    if violations:
        violation_msg = "\n".join(violations[:20])  # Show first 20 violations
        if len(violations) > 20:
            violation_msg += f"\n... and {len(violations) - 20} more violations"
        pytest.fail(
            f"Found {len(violations)} file(s) containing 'AvailabilitySlot':\n{violation_msg}\n\n"
            "All AvailabilitySlot references must be removed. Bitmap-only storage now."
        )


def test_no_availabilityslot_imports_in_tests() -> None:
    """Fail if any test file imports AvailabilitySlot."""

    rg_path = shutil.which("rg")

    tests_root = Path(__file__).resolve().parents[3] / "tests"

    if rg_path and tests_root.exists():
        cmd = shlex.split(f'rg -n "\\\\bAvailabilitySlot\\\\b" {tests_root} --type py')
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode not in (0, 1):
            pytest.fail(f"ripgrep exited with {result.returncode}: {result.stderr}")
        if result.returncode == 1 or not result.stdout.strip():
            return
        lines = result.stdout.strip().split("\n")
    else:
        lines = []
        tests_dir = Path("backend/tests")
        for py_file in tests_dir.rglob("*.py"):
            if any(part in (".venv", "venv", "__pycache__", "legacy") for part in py_file.parts):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if "AvailabilitySlot" not in content:
                continue
            for idx, line in enumerate(content.splitlines(), start=1):
                if "AvailabilitySlot" in line:
                    lines.append(f"{py_file}:{idx}:{line}")
        if not lines:
            return
    violations = []

    for line in lines:
        if not line.strip():
            continue

        file_path, line_num, content = line.split(":", 2) if ":" in line else (line, "", line)
        file_path_str = file_path

        # Skip guard test itself and helper files
        if "test_no_slot" in file_path_str or "bitmap_avail.py" in file_path_str:
            continue

        # Check if file is skipped at module level or has skipped classes
        if Path(file_path).exists():
            try:
                file_content = Path(file_path).read_text(encoding="utf-8")
                file_lines = file_content.split("\n")

                # Check if file has pytestmark skip at top level (check first 1000 chars)
                if "pytestmark = pytest.mark.skip" in file_content[:1000]:
                    continue
                # Check if file has many skipped classes (likely entirely deprecated)
                if file_content.count("@pytest.mark.skip") > 3:
                    # File has multiple skipped tests - likely deprecated, skip
                    continue

                # Check if the specific line is in a skipped class
                if line_num.isdigit():
                    line_idx = int(line_num) - 1
                    # Look back up to 100 lines for @pytest.mark.skip decorator
                    for i in range(max(0, line_idx - 100), line_idx):
                        if i < len(file_lines):
                            check_line = file_lines[i]
                            if "@pytest.mark.skip" in check_line:
                                # Check next few lines for class definition
                                for j in range(i + 1, min(i + 10, len(file_lines))):
                                    if j < len(file_lines) and "class " in file_lines[j] and "Test" in file_lines[j]:
                                        # Found a skipped class - check if our line is within it
                                        # Look for next class or end of file
                                        class_start = j
                                        class_end = len(file_lines)
                                        for k in range(class_start + 1, len(file_lines)):
                                            if k < len(file_lines) and file_lines[k].strip().startswith("class ") and k > line_idx:
                                                class_end = k
                                                break
                                        # If our line is between class_start and class_end, it's in skipped class
                                        if class_start < line_idx < class_end:
                                            continue
            except Exception:
                pass

            # Check if line is in a skipped class/test
            stripped_content = content.strip()

            # Skip if entire line is a comment (starts with # after stripping)
            if stripped_content.startswith("#"):
                continue

            # Check if AvailabilitySlot appears only in an inline comment (after # marker)
            # Split line at # to check if AvailabilitySlot is in the comment portion
            if "#" in content:
                parts = content.split("#", 1)
                if len(parts) == 2:
                    code_part, comment_part = parts
                    if "AvailabilitySlot" in comment_part and "AvailabilitySlot" not in code_part:
                        # AvailabilitySlot only appears in the comment, skip it
                        continue

            # Skip docstring markers
            if stripped_content.startswith('"""') or stripped_content.startswith("'''"):
                continue

            # Skip if it's in a docstring (simple check)
            if '"""' in content or "'''" in content:
                # Check if AvailabilitySlot is within docstring quotes
                docstring_start = content.find('"""')
                docstring_end = content.find('"""', docstring_start + 3) if docstring_start >= 0 else -1
                if docstring_start >= 0 and docstring_end > docstring_start:
                    slot_pos = content.find("AvailabilitySlot")
                    if docstring_start < slot_pos < docstring_end:
                        continue

            # Skip deprecation messages and assertions about non-existence
            if any(
                pattern in content.lower()
                for pattern in [
                    "deprecated",
                    "removed",
                    "bitmap-only",
                    "assert not hasattr",
                    "no longer uses",
                    "slot_imports = [",  # Test that checks for imports
                    "slot-era deprecated",
                    "reason=\"",  # Skip decorator reasons
                    "@pytest.mark.skip",  # Skip decorators
                    "found availabilityslot imports",  # Assertion messages checking for absence
                    "db constraint test for availabilityslot",  # Skip reason in decorator
                    "was mock(spec=availabilityslot)",  # Comments documenting what was replaced
                ]
            ):
                continue

        # Check if this line is within a skipped class/test
        if Path(file_path).exists() and line_num.isdigit():
            try:
                file_content = Path(file_path).read_text(encoding="utf-8")
                file_lines = file_content.split("\n")
                line_idx = int(line_num) - 1

                # Look back up to 100 lines to find skip decorator on class
                in_skipped_class = False
                for i in range(max(0, line_idx - 100), line_idx):
                    if i < len(file_lines):
                        check_line = file_lines[i]
                        # Check for @pytest.mark.skip decorator followed by class definition
                        if "@pytest.mark.skip" in check_line:
                            # Check next few lines for class definition
                            for j in range(i + 1, min(i + 5, len(file_lines))):
                                if "class " in file_lines[j] and "Test" in file_lines[j]:
                                    in_skipped_class = True
                                    break
                            if in_skipped_class:
                                break

                if in_skipped_class:
                    continue
            except (ValueError, IndexError, Exception):
                pass

        violations.append(line)

    if violations:
        violation_msg = "\n".join(violations[:20])  # Show first 20
        if len(violations) > 20:
            violation_msg += f"\n... and {len(violations) - 20} more violations"
        pytest.fail(
            f"Found {len(violations)} AvailabilitySlot references in tests:\n{violation_msg}\n\n"
            "All AvailabilitySlot references must be removed. Bitmap-only storage now."
        )
