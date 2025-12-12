"""
Manual script to verify lockout thresholds by simulating failures directly via Redis.

Run from repo root:
    python backend/scripts/test_lockout.py

Note: this is not a pytest test file; running it with pytest will not execute the
script body. Use `python` to see the printed thresholds.
"""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure `app` package is importable when run from repo root.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.login_protection import account_lockout  # noqa: E402

TEST_EMAIL = "lockout-test@example.com"


async def run_lockout_demo() -> None:
    # Clear any existing state
    await account_lockout.reset(TEST_EMAIL)
    print(f"Cleared state for {TEST_EMAIL}\n")

    # Simulate failures and check lockout at each threshold
    for i in range(1, 22):
        result = await account_lockout.record_failure(TEST_EMAIL)
        locked, info = await account_lockout.check_lockout(TEST_EMAIL)

        failures = result.get("failures")
        if result.get("lockout_applied"):
            print(f"Failure #{i}: LOCKOUT TRIGGERED - {result.get('lockout_seconds')}s")
        elif locked:
            print(f"Failure #{i}: Still locked - {info.get('retry_after')}s remaining")
        else:
            print(f"Failure #{i}: No lockout yet (failures: {failures})")

    # Cleanup
    await account_lockout.reset(TEST_EMAIL)
    print(f"\nCleaned up {TEST_EMAIL}")


if __name__ == "__main__":
    asyncio.run(run_lockout_demo())
