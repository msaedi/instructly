#!/usr/bin/env python3
# backend/scripts/migrate_pydantic_v2_safe.py
"""
Safe Pydantic V1 to V2 Migration Script for InstaInstru

This script takes a conservative approach:
1. Only migrates simple @validator cases
2. Identifies complex cases for manual review
3. Ensures all imports are correct

Usage:
    python scripts/migrate_pydantic_v2_safe.py           # Analyze and show what needs fixing
    python scripts/migrate_pydantic_v2_safe.py --apply   # Apply safe changes only
"""

import argparse
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ANSI color codes
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    WARNING = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def print_header(message: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{message.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_success(message: str):
    print(f"{Colors.GREEN}✅ {message}{Colors.ENDC}")


def print_warning(message: str):
    print(f"{Colors.WARNING}⚠️  {message}{Colors.ENDC}")


def print_error(message: str):
    print(f"{Colors.RED}❌ {message}{Colors.ENDC}")


def print_info(message: str):
    print(f"{Colors.CYAN}ℹ️  {message}{Colors.ENDC}")


class SafePydanticMigrator:
    """Conservative Pydantic migrator that only handles safe cases."""

    def __init__(self, apply_changes: bool = False):
        self.apply_changes = apply_changes
        self.schema_files = [
            "backend/app/schemas/instructor.py",
            "backend/app/schemas/availability.py",
            "backend/app/schemas/availability_window.py",
            "backend/app/schemas/booking.py",
            "backend/app/schemas/password_reset.py",
            "backend/app/schemas/user.py",
        ]
        self.backup_dir = Path("backend/.pydantic_backup")

        # Track what we find
        self.safe_validators = []
        self.multi_field_validators = []
        self.config_classes = []
        self.json_encoders = []
        self.min_max_items = []
        self.files_with_changes = set()

    def backup_files(self):
        """Create backup before making changes."""
        if not self.apply_changes:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / timestamp
        backup_path.mkdir(parents=True, exist_ok=True)

        for file_path in self.schema_files:
            if os.path.exists(file_path):
                relative_path = Path(file_path).relative_to("backend")
                backup_file = backup_path / relative_path
                backup_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, backup_file)

        print_success(f"Backup created at {backup_path}")
        return backup_path

    def analyze_file(self, file_path: str):
        """Analyze a file and categorize all issues."""
        if not os.path.exists(file_path):
            return

        with open(file_path, "r") as f:
            content = f.read()
            lines = content.split("\n")

        file_name = Path(file_path).name

        # Find single-field validators (safe to migrate)
        single_validator_pattern = (
            r'@validator\s*\(\s*[\'"](\w+)[\'"]\s*(?:,\s*pre\s*=\s*\w+\s*)?\)'
        )
        for i, line in enumerate(lines):
            if match := re.search(single_validator_pattern, line):
                self.safe_validators.append(
                    {
                        "file": file_name,
                        "line": i + 1,
                        "field": match.group(1),
                        "full_line": line.strip(),
                    }
                )
                self.files_with_changes.add(file_path)

        # Find multi-field validators (need manual handling)
        multi_validator_pattern = (
            r'@validator\s*\([\'"](\w+)[\'"]\s*,\s*[\'"](\w+)[\'"]'
        )
        for i, line in enumerate(lines):
            if match := re.search(multi_validator_pattern, line):
                self.multi_field_validators.append(
                    {
                        "file": file_name,
                        "line": i + 1,
                        "fields": [match.group(1), match.group(2)],
                        "full_line": line.strip(),
                    }
                )

        # Find Config classes
        for i, line in enumerate(lines):
            if re.match(r"\s*class\s+Config\s*:", line):
                # Find what's in the Config class
                config_content = []
                j = i + 1
                while j < len(lines) and (
                    lines[j].startswith("    ") or lines[j].strip() == ""
                ):
                    if lines[j].strip():
                        config_content.append(lines[j].strip())
                    j += 1

                self.config_classes.append(
                    {"file": file_name, "line": i + 1, "content": config_content}
                )
                self.files_with_changes.add(file_path)

        # Find json_encoders
        for i, line in enumerate(lines):
            if "json_encoders" in line:
                self.json_encoders.append(
                    {"file": file_name, "line": i + 1, "full_line": line.strip()}
                )

        # Find min_items/max_items
        for i, line in enumerate(lines):
            if "min_items" in line or "max_items" in line:
                self.min_max_items.append(
                    {"file": file_name, "line": i + 1, "full_line": line.strip()}
                )
                self.files_with_changes.add(file_path)

    def apply_safe_changes(self, file_path: str):
        """Apply only the safe changes to a file."""
        if not os.path.exists(file_path):
            return

        with open(file_path, "r") as f:
            content = f.read()

        original_content = content

        # 1. Simple validator replacements
        content = re.sub(
            r'@validator\s*\(\s*([\'"])(\w+)\1\s*\)',
            r"@field_validator(\1\2\1)",
            content,
        )

        # 2. min_items -> min_length, max_items -> max_length
        content = re.sub(r"\bmin_items\s*=", "min_length=", content)
        content = re.sub(r"\bmax_items\s*=", "max_length=", content)

        # 3. Update imports
        if "field_validator" in content and "from pydantic import" in content:
            # Replace validator with field_validator in imports
            content = re.sub(
                r"from pydantic import ([^;\n]*)\bvalidator\b",
                r"from pydantic import \1field_validator",
                content,
            )

        # 4. Add ConfigDict import if we have Config classes
        if "class Config:" in content and "ConfigDict" not in content:
            # Add ConfigDict to pydantic imports
            content = re.sub(
                r"(from pydantic import [^;\n]+)", r"\1, ConfigDict", content
            )

        if content != original_content:
            if self.apply_changes:
                with open(file_path, "w") as f:
                    f.write(content)
                print_success(f"Updated {file_path}")
            return True
        return False

    def generate_manual_fixes(self):
        """Generate a report of manual fixes needed."""
        manual_fixes = []

        # Multi-field validators
        if self.multi_field_validators:
            manual_fixes.append("\n📝 MULTI-FIELD VALIDATORS (need manual splitting):")
            manual_fixes.append(
                "In Pydantic V2, each field needs its own @field_validator"
            )
            for item in self.multi_field_validators:
                manual_fixes.append(f"\n  {item['file']}:{item['line']}")
                manual_fixes.append(f"  Current: {item['full_line']}")
                manual_fixes.append(
                    f"  Fix: Split into separate @field_validator decorators:"
                )
                for field in item["fields"]:
                    manual_fixes.append(f"       @field_validator('{field}')")

        # Config classes
        if self.config_classes:
            manual_fixes.append("\n📝 CONFIG CLASSES (need manual conversion):")
            manual_fixes.append(
                "Convert class Config to model_config = ConfigDict(...)"
            )
            for item in self.config_classes:
                manual_fixes.append(f"\n  {item['file']}:{item['line']}")
                manual_fixes.append("  Current content:")
                for line in item["content"]:
                    manual_fixes.append(f"    {line}")
                manual_fixes.append("  Suggested fix:")
                config_dict_parts = []
                for line in item["content"]:
                    if "orm_mode = True" in line:
                        config_dict_parts.append("from_attributes=True")
                    elif "allow_population_by_field_name = True" in line:
                        config_dict_parts.append("populate_by_name=True")
                manual_fixes.append(
                    f"    model_config = ConfigDict({', '.join(config_dict_parts)})"
                )

        # JSON encoders
        if self.json_encoders:
            manual_fixes.append("\n📝 JSON ENCODERS (need manual migration):")
            manual_fixes.append("Use @field_serializer or custom serialization")
            for item in self.json_encoders:
                manual_fixes.append(
                    f"  {item['file']}:{item['line']} - {item['full_line']}"
                )

        return "\n".join(manual_fixes)

    def run(self):
        """Run the migration process."""
        print_header("Safe Pydantic V2 Migration")

        # Analyze all files
        print_info("Analyzing schema files...")
        for file_path in self.schema_files:
            self.analyze_file(file_path)

        # Show summary
        print_header("Analysis Summary")
        print_info(f"Files analyzed: {len(self.schema_files)}")
        print_info(f"Simple validators found: {len(self.safe_validators)}")
        print_warning(f"Multi-field validators: {len(self.multi_field_validators)}")
        print_warning(f"Config classes: {len(self.config_classes)}")
        print_warning(f"JSON encoders: {len(self.json_encoders)}")
        print_info(f"min/max_items found: {len(self.min_max_items)}")

        if self.apply_changes:
            # Backup first
            backup_path = self.backup_files()

            # Apply safe changes
            print_header("Applying Safe Changes")
            files_updated = 0
            for file_path in self.files_with_changes:
                if self.apply_safe_changes(file_path):
                    files_updated += 1

            print_success(f"Updated {files_updated} files")
            print_info(f"Backup saved to: {backup_path}")
        else:
            print_warning("DRY RUN MODE - No changes made")
            print_info("Run with --apply to make changes")

        # Show manual fixes needed
        manual_fixes = self.generate_manual_fixes()
        if manual_fixes:
            print_header("Manual Fixes Required")
            print(manual_fixes)

        # Create fix script
        if self.multi_field_validators or self.config_classes or self.json_encoders:
            script_path = Path("backend/pydantic_manual_fixes.md")
            with open(script_path, "w") as f:
                f.write("# Pydantic V2 Manual Fixes Required\n\n")
                f.write("Generated by migrate_pydantic_v2_safe.py\n\n")
                f.write(manual_fixes)
            print_info(f"\nManual fix instructions saved to: {script_path}")


def main():
    parser = argparse.ArgumentParser(description="Safe Pydantic V2 Migration")
    parser.add_argument("--apply", action="store_true", help="Apply safe changes")
    args = parser.parse_args()

    print(f"{Colors.CYAN}{Colors.BOLD}")
    print("╔══════════════════════════════════════════════════════════╗")
    print("║        SAFE PYDANTIC V2 MIGRATION TOOL                   ║")
    print("║     Only applying changes we're 100% sure about! ⚡      ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")

    migrator = SafePydanticMigrator(apply_changes=args.apply)
    migrator.run()

    print(f"\n{Colors.GREEN}Safe migration complete!{Colors.ENDC}")
    print("Check the manual fixes file for remaining work.")


if __name__ == "__main__":
    main()
