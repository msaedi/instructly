#!/usr/bin/env python3
# backend/scripts/fix_multi_validators.py
"""
Emergency fix for multi-field validators that were missed
"""

import re
from pathlib import Path


def fix_availability_validators():
    """Fix the multi-field validators in availability.py and availability_window.py"""

    # Fix availability.py
    availability_path = Path("app/schemas/availability.py")
    with open(availability_path, "r") as f:
        content = f.read()

    # Replace the multi-field validator
    content = content.replace(
        "@validator('from_week_start', 'to_week_start')",
        "@field_validator('from_week_start', 'to_week_start')",
    )

    # Also need to add validator to imports if missing
    if "validator" not in content and "@validator" not in content:
        # Good, validator import was removed
        pass

    with open(availability_path, "w") as f:
        f.write(content)

    print(f"✅ Fixed {availability_path}")

    # Fix availability_window.py
    availability_window_path = Path("app/schemas/availability_window.py")
    with open(availability_window_path, "r") as f:
        content = f.read()

    # This file should already be fixed, but let's check
    if "@validator(" in content:
        content = re.sub(r"@validator\(([^)]+)\)", r"@field_validator(\1)", content)

        with open(availability_window_path, "w") as f:
            f.write(content)
        print(f"✅ Fixed {availability_window_path}")
    else:
        print(f"✓ {availability_window_path} already fixed")


if __name__ == "__main__":
    fix_availability_validators()
    print("\nNow you need to split these multi-field validators manually!")
    print("In availability.py line ~103:")
    print("  Change: @field_validator('from_week_start', 'to_week_start')")
    print("  To two separate validators:")
    print("    @field_validator('from_week_start')")
    print("    @classmethod")
    print("    def validate_monday_from(cls, v):")
    print("        if v.weekday() != 0:")
    print("            raise ValueError('Week start dates must be Mondays')")
    print("        return v")
    print("")
    print("    @field_validator('to_week_start')")
    print("    @classmethod")
    print("    def validate_monday_to(cls, v):")
    print("        if v.weekday() != 0:")
    print("            raise ValueError('Week start dates must be Mondays')")
    print("        return v")
