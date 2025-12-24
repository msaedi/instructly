#!/usr/bin/env python3
"""
Pre-commit hook to detect Stripe calls inside DB transactions.

Blocks commits where Stripe API calls appear inside transaction blocks.
This enforces the 3-phase pattern documented in architecture-decisions.md (v123).

Pattern:
  Phase 1: Read/validate (quick transaction ~5ms)
  Phase 2: Stripe calls (NO transaction - network latency 100-500ms)
  Phase 3: Write results (quick transaction ~5ms)

Usage:
  python scripts/check_stripe_transaction_pattern.py
"""
from pathlib import Path
import re
import sys

# Patterns that indicate Stripe API calls
STRIPE_CALL_PATTERNS = [
    r"stripe\.PaymentIntent\.(create|confirm|cancel|capture)",
    r"stripe\.PaymentMethod\.(attach|detach|retrieve)",
    r"stripe\.Customer\.create",
    r"stripe\.Transfer\.create_reversal",
    r"stripe\.Refund\.create",
]

# Files to check for Stripe transaction violations
SERVICE_FILES = [
    Path("app/services/booking_service.py"),
    Path("app/services/stripe_service.py"),
    Path("app/services/review_service.py"),
]

# Marker comment to explicitly allow Stripe call inside transaction
# (should rarely be used - only for atomic operations that truly need it)
ALLOW_MARKER = "# stripe-inside-tx-ok"


def check_file(filepath: Path) -> list[str]:
    """Check a file for Stripe calls inside transactions."""
    if not filepath.exists():
        return []

    violations = []
    content = filepath.read_text()
    lines = content.split("\n")

    # Track transaction block depth using indentation
    in_transaction = False
    transaction_indent = 0
    transaction_start_line = 0

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith("#"):
            continue

        # Calculate current indentation
        leading_spaces = len(line) - len(line.lstrip())

        # Detect transaction block start
        if "with self.transaction()" in line:
            in_transaction = True
            transaction_indent = leading_spaces
            transaction_start_line = i
            continue

        # Detect transaction block end (dedent back to transaction level or less)
        if in_transaction and stripped and leading_spaces <= transaction_indent:
            # Only reset if we're actually on a new statement (not a continuation)
            if not stripped.startswith(")") and not stripped.startswith("]"):
                in_transaction = False
                transaction_indent = 0
                transaction_start_line = 0

        # Check for Stripe calls inside transaction
        if in_transaction:
            for pattern in STRIPE_CALL_PATTERNS:
                if re.search(pattern, stripped):
                    # Check for explicit allow marker
                    if ALLOW_MARKER in stripped:
                        continue

                    # Check if this is a helper method call (allowed)
                    if "_execute_cancellation_stripe_calls" in stripped:
                        continue
                    if "_execute_stripe_calls" in stripped:
                        continue

                    violations.append(
                        f"  {filepath}:{i}: {stripped[:60]}...\n"
                        f"    ↳ Transaction started at line {transaction_start_line}"
                    )

    return violations


def main() -> int:
    """Run the check on all service files."""
    all_violations: list[str] = []

    for filepath in SERVICE_FILES:
        violations = check_file(filepath)
        all_violations.extend(violations)

    if all_violations:
        print("❌ Stripe calls detected inside DB transactions!")
        print()
        print("The 3-phase pattern requires Stripe calls OUTSIDE transactions:")
        print("  Phase 1: Read (quick transaction ~5ms)")
        print("  Phase 2: Stripe calls (NO transaction)")
        print("  Phase 3: Write (quick transaction ~5ms)")
        print()
        print("See: docs/architecture/architecture-decisions.md (v123)")
        print()
        print("Violations:")
        for v in all_violations:
            print(v)
        print()
        print(f"To allow a specific call, add '{ALLOW_MARKER}' comment to the line.")
        return 1

    print("✅ No Stripe calls inside transactions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
