#!/usr/bin/env python3
# backend/scripts/cleanup.py
"""
Cleanup script for InstaInstru
- Removes duplicate database indexes
- Finds unused imports
- Identifies completed TODOs
"""

import os
import sys
import re
import ast
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.database import engine


def cleanup_duplicate_indexes():
    """Remove duplicate database indexes."""
    print("\n🗄️  Cleaning up duplicate database indexes...")
    
    drop_queries = [
        "DROP INDEX IF EXISTS idx_date_time_slots_date_override_id;",
        "DROP INDEX IF EXISTS idx_availability_slots_availability_id;",
        "DROP INDEX IF EXISTS idx_specific_date_availability_instructor_date;"
    ]
    
    with engine.connect() as conn:
        for query in drop_queries:
            try:
                conn.execute(text(query))
                conn.commit()
                print(f"✅ Executed: {query}")
            except Exception as e:
                print(f"❌ Failed: {query} - {str(e)}")


def find_unused_imports(directory="backend/app/services"):
    """Find potentially unused imports in service files."""
    print(f"\n🔍 Checking for unused imports in {directory}...")
    
    unused_imports = []
    
    for filepath in Path(directory).glob("*.py"):
        if filepath.name == "__init__.py":
            continue
            
        with open(filepath, 'r') as f:
            content = f.read()
        
        try:
            tree = ast.parse(content)
            
            # Get all imports
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name.split('.')[0])
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        imports.append(alias.name)
            
            # Check if imports are used
            for imp in set(imports):
                # Simple check - look for the import name in the rest of the code
                # This is not perfect but catches obvious cases
                if content.count(imp) == 1:  # Only appears in import line
                    unused_imports.append(f"{filepath.name}: {imp}")
                    
        except Exception as e:
            print(f"❌ Error parsing {filepath.name}: {str(e)}")
    
    if unused_imports:
        print("\nPotentially unused imports found:")
        for imp in unused_imports:
            print(f"  - {imp}")
    else:
        print("✅ No obviously unused imports found")
    
    return unused_imports


def find_completed_todos(directory="backend"):
    """Find TODO comments that might already be done."""
    print(f"\n📝 Checking for completed TODOs in {directory}...")
    
    todo_pattern = re.compile(r'#\s*(TODO|FIXME):\s*(.+)', re.IGNORECASE)
    todos = []
    
    for filepath in Path(directory).rglob("*.py"):
        if "venv" in str(filepath) or "__pycache__" in str(filepath):
            continue
            
        try:
            with open(filepath, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    match = todo_pattern.search(line)
                    if match:
                        todos.append({
                            'file': str(filepath.relative_to(directory)),
                            'line': line_num,
                            'type': match.group(1).upper(),
                            'text': match.group(2).strip()
                        })
        except Exception as e:
            print(f"❌ Error reading {filepath}: {str(e)}")
    
    # Check for potentially completed TODOs
    completed_keywords = ['done', 'fixed', 'implemented', 'completed']
    
    print(f"\nFound {len(todos)} total TODOs/FIXMEs")
    
    # Look for TODOs that might be done
    possibly_done = []
    for todo in todos:
        # Check if TODO mentions something that's likely done
        if any(keyword in todo['text'].lower() for keyword in completed_keywords):
            possibly_done.append(todo)
        # Check common patterns
        elif 'redis' in todo['text'].lower() and 'dragonfly' in todo['text'].lower():
            possibly_done.append(todo)  # We decided on DragonflyDB
    
    if possibly_done:
        print("\n🤔 TODOs that might be completed:")
        for todo in possibly_done:
            print(f"  - {todo['file']}:{todo['line']} - {todo['type']}: {todo['text']}")
    
    # Show a sample of other TODOs
    print("\n📋 Sample of other TODOs:")
    for todo in todos[:10]:
        if todo not in possibly_done:
            print(f"  - {todo['file']}:{todo['line']} - {todo['type']}: {todo['text']}")
    
    return todos


def run_linter_command():
    """Print command to run a proper linter."""
    print("\n🧹 For comprehensive linting, run:")
    print("  pip install flake8 flake8-unused-arguments")
    print("  flake8 backend/app/services --extend-ignore=E501")
    print("\nOr for more thorough analysis:")
    print("  pip install pylint")
    print("  pylint backend/app/services")


if __name__ == "__main__":
    print("🚀 InstaInstru Cleanup Script")
    print("=" * 50)
    
    # 1. Clean database indexes
    try:
        cleanup_duplicate_indexes()
    except Exception as e:
        print(f"❌ Database cleanup failed: {str(e)}")
    
    # 2. Find unused imports
    find_unused_imports()
    
    # 3. Find completed TODOs
    find_completed_todos()
    
    # 4. Suggest proper linting
    run_linter_command()
    
    print("\n✅ Cleanup complete!")
    print("\nNext steps:")
    print("1. Review and remove any confirmed unused imports")
    print("2. Remove or update completed TODOs")
    print("3. Run a full linter for comprehensive analysis")