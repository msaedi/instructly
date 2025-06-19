# backend/tests/test_warning_diagnostics.py
"""
Diagnostic test to identify which imports trigger warnings.
Run from backend directory: python -m pytest tests/test_warning_diagnostics.py -v
"""

import os
import sys
import warnings

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_imports_after_config_fix():
    """Test imports after fixing config.py."""

    print("\n=== Testing imports after config.py fix ===")

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        # This should no longer trigger the Pydantic warning

        print(f"Total warnings: {len(w)}")

        pydantic_warnings = [
            warning
            for warning in w
            if "PydanticDeprecatedSince20" in str(warning.message)
        ]
        urllib_warnings = [
            warning for warning in w if "urllib3" in str(warning.message)
        ]

        print(f"Pydantic warnings: {len(pydantic_warnings)}")
        print(f"urllib3 warnings: {len(urllib_warnings)}")

        for warning in w:
            print(f"\nWarning: {warning.category.__name__}")
            print(f"Message: {warning.message}")
            print(f"File: {warning.filename}:{warning.lineno}")


def test_email_service_urllib_warning():
    """Isolate urllib3 warning source."""

    print("\n=== Testing urllib3 warning source ===")

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        # Test different imports
        print("1. Testing resend import...")
        try:
            urllib_count = len([w for w in w if "urllib3" in str(w.message)])
            print(f"   urllib3 warnings after resend: {urllib_count}")
        except ImportError:
            print("   Resend not installed")

        print("2. Testing email service...")
        try:
            new_count = len([w for w in w if "urllib3" in str(w.message)])
            print(f"   urllib3 warnings after email service: {new_count}")
        except ImportError as e:
            print(f"   Error: {e}")


if __name__ == "__main__":
    test_imports_after_config_fix()
    test_email_service_urllib_warning()
