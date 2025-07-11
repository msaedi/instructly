#!/usr/bin/env python3
"""
Service Layer Dead Code Cleanup Script
Safely removes all confirmed dead code from the InstaInstru service layer.

This script will:
1. Create backups of files before deletion
2. Verify no imports exist for files being deleted
3. Run tests to ensure nothing breaks
4. Provide a rollback option if needed
"""
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

# Files confirmed as dead code after thorough analysis
DEAD_FILES = [
    "backend/app/services/notification_service_backup.py",  # Backup file
    "backend/app/services/availability_service_cached.py",  # Example/demo file never used
]

# Files that might look dead but are actually still in use
KEEP_FILES = [
    "backend/app/services/email.py",  # Still imported by notification_service.py and password_reset_service.py
]

# Create backup directory with timestamp
BACKUP_DIR = f"backend/dead_code_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def create_backup():
    """Backup files before deletion for safety."""
    print(f"\n📦 Creating backup directory: {BACKUP_DIR}")
    os.makedirs(BACKUP_DIR, exist_ok=True)

    for filepath in DEAD_FILES:
        if os.path.exists(filepath):
            # Create subdirectory structure in backup
            rel_path = os.path.relpath(filepath, "backend")
            backup_path = os.path.join(BACKUP_DIR, rel_path)
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)

            # Copy file to backup
            shutil.copy2(filepath, backup_path)
            print(f"   ✅ Backed up: {filepath}")
        else:
            print(f"   ⚠️  File not found: {filepath}")


def verify_no_imports(filepath):
    """Double-check file has no imports before deletion."""
    filename = os.path.basename(filepath)
    module_name = filename.replace(".py", "")

    print(f"\n🔍 Verifying no imports for: {module_name}")

    # Search for various import patterns
    patterns = [
        f"from app.services.{module_name} import",
        f"from app.services import {module_name}",
        f"import {module_name}",
        f"services.{module_name}",
    ]

    found_imports = False
    for pattern in patterns:
        cmd = [
            "grep",
            "-r",
            pattern,
            "backend/",
            "--exclude-dir=__pycache__",
            "--exclude-dir=htmlcov",
            "--exclude-dir=dead_code_backup*",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.stdout:
            # Filter out the file importing itself and coverage reports
            imports = [
                line
                for line in result.stdout.strip().split("\n")
                if filepath not in line and "coverage" not in line.lower()
            ]

            if imports:
                print(f"   ❌ Found imports with pattern '{pattern}':")
                for imp in imports[:3]:  # Show first 3 imports
                    print(f"      {imp}")
                found_imports = True

    if not found_imports:
        print(f"   ✅ No imports found - safe to delete")

    return not found_imports


def remove_dead_code():
    """Remove all confirmed dead files."""
    print("\n🗑️  Removing dead code files...")

    removed_count = 0
    total_bytes = 0

    for filepath in DEAD_FILES:
        if os.path.exists(filepath):
            # Get file size before deletion
            file_size = os.path.getsize(filepath)

            # Verify it's safe to delete
            if verify_no_imports(filepath):
                os.remove(filepath)
                removed_count += 1
                total_bytes += file_size
                print(f"   ✅ Deleted: {filepath} ({file_size:,} bytes)")
            else:
                print(f"   ❌ Skipped: {filepath} (has active imports)")
        else:
            print(f"   ⚠️  Already deleted or not found: {filepath}")

    print(f"\n📊 Summary: Removed {removed_count} files, {total_bytes:,} bytes ({total_bytes/1024:.1f}KB)")


def cleanup_pycache():
    """Remove all __pycache__ directories in services."""
    print("\n🧹 Cleaning up __pycache__ directories...")

    pycache_dirs = list(Path("backend/app/services").rglob("__pycache__"))

    if pycache_dirs:
        for pycache in pycache_dirs:
            shutil.rmtree(pycache)
            print(f"   ✅ Removed: {pycache}")
    else:
        print("   ✅ No __pycache__ directories found")


def run_import_test():
    """Test that all service imports still work."""
    print("\n🧪 Testing service imports...")

    test_code = """
import sys
sys.path.insert(0, 'backend')

try:
    # Test importing all services
    from app.services import *
    print("   ✅ All service imports successful")
except ImportError as e:
    print(f"   ❌ Import error: {e}")
    sys.exit(1)

# Test specific imports that use email.py
try:
    from app.services.notification_service import NotificationService
    from app.services.password_reset_service import PasswordResetService
    from app.services.email import EmailService
    print("   ✅ Email-related services import correctly")
except ImportError as e:
    print(f"   ❌ Email service import error: {e}")
    sys.exit(1)
"""

    result = subprocess.run([sys.executable, "-c", test_code], capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(f"   ⚠️  Warnings: {result.stderr}")

    return result.returncode == 0


def run_service_tests():
    """Run service tests to ensure nothing broke."""
    print("\n🧪 Running service tests...")

    # Run unit tests
    cmd = ["pytest", "backend/tests/unit/services/", "-xvs", "--tb=short"]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print("   ✅ Unit tests passed")
    else:
        print("   ❌ Unit tests failed")
        print(result.stdout[-500:])  # Last 500 chars of output
        return False

    # Run integration tests
    cmd = ["pytest", "backend/tests/integration/services/", "-xvs", "--tb=short", "-k", "not cache"]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print("   ✅ Integration tests passed")
        return True
    else:
        print("   ❌ Integration tests failed")
        print(result.stdout[-500:])  # Last 500 chars of output
        return False


def final_verification():
    """Run final checks to ensure everything is clean."""
    print("\n✅ Final verification...")

    # Count service files
    service_files = list(Path("backend/app/services").glob("*.py"))
    print(f"   📁 Service files remaining: {len(service_files)}")

    # List all services
    print("   📄 Active services:")
    for f in sorted(service_files):
        size = os.path.getsize(f)
        print(f"      - {f.name} ({size:,} bytes)")

    # Verify critical files still exist
    critical_files = [
        "backend/app/services/email.py",
        "backend/app/services/notification_service.py",
        "backend/app/services/password_reset_service.py",
        "backend/app/services/base.py",
        "backend/app/services/dependencies.py",
    ]

    print("\n   🔒 Critical files check:")
    all_exist = True
    for filepath in critical_files:
        if os.path.exists(filepath):
            print(f"      ✅ {os.path.basename(filepath)}")
        else:
            print(f"      ❌ {os.path.basename(filepath)} - MISSING!")
            all_exist = False

    return all_exist


def rollback():
    """Restore backed up files if something went wrong."""
    print(f"\n⏮️  Rolling back from {BACKUP_DIR}...")

    if not os.path.exists(BACKUP_DIR):
        print("   ❌ Backup directory not found!")
        return False

    # Restore each file
    for filepath in DEAD_FILES:
        rel_path = os.path.relpath(filepath, "backend")
        backup_path = os.path.join(BACKUP_DIR, rel_path)

        if os.path.exists(backup_path):
            shutil.copy2(backup_path, filepath)
            print(f"   ✅ Restored: {filepath}")
        else:
            print(f"   ⚠️  No backup found for: {filepath}")

    return True


def main():
    """Main cleanup process with safety checks."""
    print("🧹 InstaInstru Service Layer Dead Code Cleanup")
    print("=" * 50)

    # Show what will be deleted
    print("\n📋 Files to be deleted:")
    for f in DEAD_FILES:
        if os.path.exists(f):
            size = os.path.getsize(f)
            print(f"   - {f} ({size:,} bytes)")

    print("\n⚠️  Files that will be KEPT (not dead code):")
    for f in KEEP_FILES:
        print(f"   - {f}")

    # Get confirmation
    response = input("\n❓ Proceed with cleanup? (yes/no): ").lower().strip()
    if response != "yes":
        print("❌ Cleanup cancelled")
        return

    # Create backup
    create_backup()

    # Test imports before deletion
    if not run_import_test():
        print("❌ Import test failed before cleanup - aborting")
        return

    # Remove dead code
    remove_dead_code()

    # Clean pycache
    cleanup_pycache()

    # Test imports after deletion
    if not run_import_test():
        print("❌ Import test failed after cleanup - rolling back")
        rollback()
        return

    # Run tests
    tests_passed = run_service_tests()

    # Final verification
    if final_verification() and tests_passed:
        print("\n✅ Service layer cleanup completed successfully!")
        print(f"💾 Backup saved to: {BACKUP_DIR}")
        print("🎉 The service layer is now pristine!")
    else:
        print("\n❌ Issues detected - consider rolling back")
        response = input("❓ Rollback changes? (yes/no): ").lower().strip()
        if response == "yes":
            if rollback():
                print("✅ Rollback completed")
            else:
                print("❌ Rollback failed - check backup directory manually")


if __name__ == "__main__":
    import sys

    # Ensure we're in the project root
    if not os.path.exists("backend/app/services"):
        print("❌ Error: Must run from project root directory")
        print("   Current directory:", os.getcwd())
        sys.exit(1)

    main()
