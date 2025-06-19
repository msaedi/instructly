#!/usr/bin/env python3
"""
Find all occurrences of 'Instructly' in the codebase to ensure complete rebranding.
"""

import os
import re
from pathlib import Path


def find_brand_occurrences(root_path="."):
    """Find all occurrences of 'Instructly' (case-insensitive) in code files."""

    # File extensions to search
    extensions = [
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".html",
        ".css",
        ".json",
        ".md",
        ".txt",
        ".env",
    ]

    # Directories to skip
    skip_dirs = {
        "node_modules",
        "venv",
        ".git",
        "__pycache__",
        ".next",
        "build",
        "dist",
        ".venv",
        "env",
    }

    occurrences = []

    for root, dirs, files in os.walk(root_path):
        # Skip certain directories
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                file_path = Path(root) / file
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    # Find all occurrences (case-insensitive)
                    matches = list(re.finditer(r"instructly", content, re.IGNORECASE))

                    if matches:
                        # Get line numbers for each match
                        lines = content.split("\n")
                        for match in matches:
                            line_num = content[: match.start()].count("\n") + 1
                            line_content = lines[line_num - 1].strip()

                            occurrences.append(
                                {
                                    "file": str(file_path),
                                    "line": line_num,
                                    "content": line_content,
                                    "match": match.group(),
                                }
                            )

                except Exception:
                    pass

    return occurrences


def main():
    print("Searching for 'Instructly' occurrences in the codebase...")
    print("=" * 80)

    # Get the project root - look for 'instructly' in the path
    current_dir = Path.cwd()

    # Find project root by looking for a directory that contains both 'backend' and 'frontend'
    project_root = current_dir
    while project_root.parent != project_root:
        if (project_root / "backend").exists() and (project_root / "frontend").exists():
            break
        project_root = project_root.parent

    # If we couldn't find it, try common patterns
    if not (
        (project_root / "backend").exists() and (project_root / "frontend").exists()
    ):
        # Maybe we're in backend/scripts
        if current_dir.name == "scripts" and current_dir.parent.name == "backend":
            project_root = current_dir.parent.parent
        elif current_dir.name == "backend":
            project_root = current_dir.parent
        else:
            project_root = current_dir

    print(f"Searching in: {project_root}")
    print(f"Backend exists: {(project_root / 'backend').exists()}")
    print(f"Frontend exists: {(project_root / 'frontend').exists()}")
    print()

    # Search entire project
    all_occurrences = find_brand_occurrences(project_root)

    if not all_occurrences:
        print("No occurrences of 'Instructly' found!")
        return

    # Group by file
    files_with_occurrences = {}
    for occ in all_occurrences:
        file_path = occ["file"]
        if file_path not in files_with_occurrences:
            files_with_occurrences[file_path] = []
        files_with_occurrences[file_path].append(occ)

    # Categorize files
    backend_files = []
    frontend_files = []
    config_files = []
    doc_files = []

    for file_path in files_with_occurrences:
        if "backend" in file_path:
            backend_files.append(file_path)
        elif "frontend" in file_path:
            frontend_files.append(file_path)
        elif any(x in file_path for x in [".env", "package.json", ".json"]):
            config_files.append(file_path)
        elif any(x in file_path for x in [".md", "README", ".txt"]):
            doc_files.append(file_path)

    # Display results by category
    if backend_files:
        print("🔧 Backend Files:")
        print("-" * 40)
        for file_path in sorted(backend_files):
            print(f"📄 {file_path}")
            for occ in files_with_occurrences[file_path][
                :3
            ]:  # Show first 3 occurrences
                print(f"  Line {occ['line']}: {occ['content'][:80]}...")
            if len(files_with_occurrences[file_path]) > 3:
                print(
                    f"  ... and {len(files_with_occurrences[file_path]) - 3} more occurrences"
                )
            print()

    if frontend_files:
        print("\n💻 Frontend Files:")
        print("-" * 40)
        for file_path in sorted(frontend_files):
            print(f"📄 {file_path}")
            for occ in files_with_occurrences[file_path][:3]:
                print(f"  Line {occ['line']}: {occ['content'][:80]}...")
            if len(files_with_occurrences[file_path]) > 3:
                print(
                    f"  ... and {len(files_with_occurrences[file_path]) - 3} more occurrences"
                )
            print()

    if config_files:
        print("\n⚙️  Configuration Files:")
        print("-" * 40)
        for file_path in sorted(config_files):
            print(f"📄 {file_path}")
            for occ in files_with_occurrences[file_path][:3]:
                print(f"  Line {occ['line']}: {occ['content'][:80]}...")
            print()

    if doc_files:
        print("\n📚 Documentation Files:")
        print("-" * 40)
        for file_path in sorted(doc_files):
            print(f"📄 {file_path}")
            for occ in files_with_occurrences[file_path][:3]:
                print(f"  Line {occ['line']}: {occ['content'][:80]}...")
            print()

    print("\n" + "=" * 80)
    print(f"Total occurrences: {len(all_occurrences)}")
    print(f"Files affected: {len(files_with_occurrences)}")
    print(f"  Backend: {len(backend_files)} files")
    print(f"  Frontend: {len(frontend_files)} files")
    print(f"  Config: {len(config_files)} files")
    print(f"  Docs: {len(doc_files)} files")

    # Priority files that need manual attention
    print("\n🎯 Priority files that need manual updates:")
    priority_patterns = ["package.json", ".env", "README", "index.html"]
    priority_files = []
    for file_path in files_with_occurrences:
        if any(pattern in file_path for pattern in priority_patterns):
            priority_files.append(file_path)

    for file in sorted(priority_files):
        print(f"  - {file}")


if __name__ == "__main__":
    main()
