#!/usr/bin/env python3
# backend/scripts/find_availability_slot_id_references.py
"""
Script to find all remaining references to availability_slot_id in the codebase.

This helps identify code that wasn't updated after Session v56 removed
the availability_slot_id field from the Booking model.
"""

import os
import re
from typing import List, Tuple


def find_references(root_dir: str = "backend") -> List[Tuple[str, int, str]]:
    """
    Find all references to availability_slot_id in Python files.

    Returns:
        List of (filepath, line_number, line_content) tuples
    """
    references = []

    # Patterns to search for
    patterns = [
        r"availability_slot_id",
        r"booking\.availability_slot\b",  # Relationship reference
        r"Booking\.availability_slot_id",
        r"availability_slot_id\.label",
    ]

    # Compile regex patterns
    compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]

    # Walk through Python files
    for root, dirs, files in os.walk(root_dir):
        # Skip test files for now (focus on implementation)
        if "test" in root:
            continue

        # Skip migration files
        if "alembic" in root or "versions" in root:
            continue

        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)

                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        for line_num, line in enumerate(f, 1):
                            for pattern in compiled_patterns:
                                if pattern.search(line):
                                    references.append((filepath, line_num, line.strip()))
                                    break
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")

    return references


def categorize_references(references: List[Tuple[str, int, str]]) -> dict:
    """Categorize references by file type."""
    categories = {"models": [], "repositories": [], "services": [], "routes": [], "schemas": [], "other": []}

    for filepath, line_num, line in references:
        if "/models/" in filepath:
            categories["models"].append((filepath, line_num, line))
        elif "/repositories/" in filepath:
            categories["repositories"].append((filepath, line_num, line))
        elif "/services/" in filepath:
            categories["services"].append((filepath, line_num, line))
        elif "/routes/" in filepath:
            categories["routes"].append((filepath, line_num, line))
        elif "/schemas/" in filepath:
            categories["schemas"].append((filepath, line_num, line))
        else:
            categories["other"].append((filepath, line_num, line))

    return categories


def main():
    """Find and report all availability_slot_id references."""
    print("🔍 Searching for availability_slot_id references...\n")

    references = find_references()

    if not references:
        print("✅ No references to availability_slot_id found!")
        return

    print(f"❌ Found {len(references)} references to availability_slot_id:\n")

    # Categorize and display
    categories = categorize_references(references)

    for category, refs in categories.items():
        if refs:
            print(f"\n📁 {category.upper()} ({len(refs)} references):")
            print("-" * 80)

            for filepath, line_num, line in refs:
                # Extract just the relevant path
                short_path = filepath.replace("backend/", "")
                print(f"{short_path}:{line_num}")
                print(f"  {line}\n")

    # Summary
    print("\n📊 SUMMARY:")
    print("-" * 40)
    for category, refs in categories.items():
        if refs:
            print(f"{category}: {len(refs)} references")

    print(f"\nTotal: {len(references)} references need to be updated")

    # Specific recommendations
    print("\n💡 RECOMMENDATIONS:")
    print("-" * 40)

    if categories["repositories"]:
        print("1. Repository fixes needed:")
        repo_files = set(ref[0] for ref in categories["repositories"])
        for repo_file in repo_files:
            print(f"   - {repo_file.replace('backend/', '')}")

    if categories["services"]:
        print("\n2. Service fixes needed:")
        service_files = set(ref[0] for ref in categories["services"])
        for service_file in service_files:
            print(f"   - {service_file.replace('backend/', '')}")

    if categories["schemas"]:
        print("\n3. Schema updates needed:")
        schema_files = set(ref[0] for ref in categories["schemas"])
        for schema_file in schema_files:
            print(f"   - {schema_file.replace('backend/', '')}")


if __name__ == "__main__":
    main()
