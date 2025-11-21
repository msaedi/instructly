#!/usr/bin/env python3
"""
Project cleanup script to remove debug artifacts and optimize codebase.
"""

import os
from pathlib import Path
import re


def remove_debug_logging():
    """Remove or comment out debug logging statements."""
    files_to_check = [
        "backend/app/services/bulk_operation_service.py",
    ]

    for file_path in files_to_check:
        if os.path.exists(file_path):
            print(f"Cleaning {file_path}...")
            with open(file_path, "r") as f:
                content = f.read()

            # Remove the debug logging block
            content = re.sub(
                r'\n\s*# ADD THIS DEBUG LOGGING\n\s*self\.logger\.info\("Bulk update operations:.*?\n\s*self\.logger\.info\(f"\s*Operation:.*?\)\n',
                "\n",
                content,
                flags=re.DOTALL,
            )

            with open(file_path, "w") as f:
                f.write(content)
            print("  ✓ Removed debug logging")


def find_unused_imports():
    """Find potentially unused imports."""
    print("\nChecking for potentially unused TYPE_CHECKING imports...")

    service_files = Path("backend/app/services").glob("*.py")
    for file in service_files:
        with open(file, "r") as f:
            content = f.read()

        if "TYPE_CHECKING" in content and "CacheService" in content:
            # Simple count of CacheService usage
            type_checking_block = "if TYPE_CHECKING:" in content
            cache_service_uses = content.count("CacheService")

            if type_checking_block and cache_service_uses > 1:
                print(f"  ✓ {file.name}: TYPE_CHECKING imports look correct ({cache_service_uses} uses)")


def check_frontend_logging():
    """Report on frontend logging usage."""
    print("\nFrontend logging summary:")

    # Count different log levels
    log_levels = ["debug", "info", "warn", "error"]
    for level in log_levels:
        cmd = f'grep -r "logger.{level}" frontend/app/ --include="*.tsx" --include="*.ts" 2>/dev/null | wc -l'
        count = os.popen(cmd).read().strip()
        print(f"  logger.{level}: {count} occurrences")


def setup_log_levels():
    """Create environment-based logging configuration."""
    print("\nSetting up environment-based logging...")

    _logger_config = """// frontend/lib/logger.ts
// Add this at the top of your logger configuration

const LOG_LEVELS = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3,
} as const;

// Set log level based on environment
const getLogLevel = () => {
  if (process.env.NODE_ENV === 'production') {
    return LOG_LEVELS.INFO;
  }
  return LOG_LEVELS.DEBUG;
};

const currentLevel = getLogLevel();

// Update your logger methods to check level:
export const logger = {
  debug: (message: string, data?: any) => {
    if (currentLevel <= LOG_LEVELS.DEBUG) {
      console.log(`[DEBUG] ${message}`, data);
    }
  },
  info: (message: string, data?: any) => {
    if (currentLevel <= LOG_LEVELS.INFO) {
      console.log(`[INFO] ${message}`, data);
    }
  },
  // ... etc
};
"""
    print("  ℹ️  Add environment-based log levels to frontend/lib/logger.ts")
    print("     (See suggested configuration above)")


def main():
    print("🧹 iNSTAiNSTRU Project Cleanup")
    print("=" * 40)

    # Run cleanup tasks
    remove_debug_logging()
    find_unused_imports()
    check_frontend_logging()
    setup_log_levels()

    print("\n✅ Cleanup complete!")
    print("\nManual tasks remaining:")
    print("1. Update frontend/lib/logger.ts with environment-based levels")
    print("2. Run tests to ensure nothing broke: pytest backend/tests/")
    print("3. Commit these cleanup changes")


if __name__ == "__main__":
    main()
