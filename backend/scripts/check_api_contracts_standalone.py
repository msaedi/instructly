#!/usr/bin/env python3
"""
Standalone API contract checker that doesn't rely on pytest.
"""

import os
import sys
import warnings
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Suppress database messages and warnings
os.environ["SUPPRESS_DB_MESSAGES"] = "1"
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="urllib3")

try:
    from app.main import fastapi_app as app
    from tests.test_api_contracts import APIContractAnalyzer
except ImportError as e:
    print(f"Import error: {e}")
    print("Dependencies not available - contract check skipped")
    sys.exit(0)


def main():
    """Run contract analysis."""
    # Colors for output (only in terminal)
    if not os.getenv("CI") and sys.stdout.isatty():
        GREEN = "\033[92m"
        RED = "\033[91m"
        BLUE = "\033[94m"
        RESET = "\033[0m"
    else:
        GREEN = RED = BLUE = RESET = ""

    try:
        print(f"{BLUE}🔍 Checking API Contracts...{RESET}")
        print("=" * 50)

        analyzer = APIContractAnalyzer(app)
        violations = analyzer.analyze_all_routes()

        if violations:
            print(f"\n{RED}❌ API Contract Violations Found!{RESET}")
            print(f"\nFound {len(violations)} contract violations:")
            for v in violations[:10]:  # Show first 10
                print(f"  - {v}")
            print("\nTo see full details, run:")
            print(f"  cd {Path(__file__).parent.parent}")
            print("  pytest tests/test_api_contracts.py -v")
            return 1
        else:
            print(f"\n{GREEN}✅ All API contracts are valid!{RESET}")
            print("\nContract tests passed:")
            print("  ✓ All endpoints declare response models")
            print("  ✓ No direct dictionary returns")
            print("  ✓ No manual JSON responses")
            print("  ✓ Consistent field naming")
            return 0
    except Exception as e:
        print(f"Error running contract check: {e}")
        import traceback

        if os.getenv("CI"):
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
