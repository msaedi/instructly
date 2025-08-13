#!/usr/bin/env python3
"""
CI Privacy Audit Script - Thin GitHub Actions wrapper for privacy auditor.

This lightweight script wraps the core privacy auditor module for CI/CD use.
All heavy lifting is done by app.core.privacy_auditor.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Check for CI mode early to disable logging before imports
if "--ci" in sys.argv:
    logging.getLogger().setLevel(logging.CRITICAL)
    # Also disable specific loggers
    logging.getLogger("app.core.privacy_auditor").setLevel(logging.CRITICAL)
    logging.getLogger("httpx").setLevel(logging.CRITICAL)

from app.core.privacy_auditor import ViolationSeverity, run_privacy_audit


class ExitCode:
    """Exit codes for CI/CD integration."""

    SUCCESS = 0
    PRIVACY_VIOLATION = 1
    SETUP_ERROR = 2


async def main():
    """Main entry point - thin wrapper around core auditor."""
    parser = argparse.ArgumentParser(description="Privacy audit for CI/CD")

    parser.add_argument("--quiet", "-q", action="store_true", help="Minimal output")
    parser.add_argument("--verbose", "-v", action="store_true", help="Detailed output")
    parser.add_argument("--ci", action="store_true", help="CI mode with JSON output")
    parser.add_argument("--fail-fast", action="store_true", help="Fail on any violation")
    parser.add_argument("--config", help="Path to configuration file")
    parser.add_argument("--category", choices=["public", "auth", "admin"], help="Test specific category only")
    parser.add_argument("--endpoint", help="Test specific endpoint only")

    args = parser.parse_args()

    # Determine base URL from environment or default
    base_url = os.getenv("API_BASE_URL", "http://localhost:8000")

    # GitHub Actions detection
    is_github_actions = os.getenv("GITHUB_ACTIONS") == "true"

    try:
        # Run the core auditor
        result, report = await run_privacy_audit(
            base_url=base_url,
            test_mode=True,  # Always test mode in CI
            config_file=args.config,
            verbose=args.verbose,
            output_format="json" if args.ci else "markdown",
            filter_category=args.category,
            filter_endpoint=args.endpoint,
        )

        # Save reports as artifacts in logs directory
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)

        Path(logs_dir / "privacy_audit_report.json").write_text(json.dumps(result.to_dict(), indent=2, default=str))
        # For markdown report, use the one we already generated if not in CI mode
        if args.ci:
            # In CI mode, we need to generate markdown separately
            from app.core.privacy_auditor import PrivacyAuditor

            auditor = PrivacyAuditor(base_url=base_url)
            try:
                markdown_report = auditor.generate_report(result, format="markdown")
                Path(logs_dir / "privacy_audit_report.md").write_text(markdown_report)
            finally:
                await auditor.close()
        else:
            Path(logs_dir / "privacy_audit_report.md").write_text(report)

        # Output based on mode
        if args.ci:
            print(json.dumps(result.to_dict(), default=str))
        elif args.quiet:
            if result.violations:
                print(f"❌ Found {len(result.violations)} privacy violations")
            else:
                print("✅ No privacy violations found")
        else:
            print(report)

        # GitHub Actions specific outputs
        if is_github_actions:
            with open(os.environ.get("GITHUB_OUTPUT", "github_output.txt"), "a") as f:
                f.write(f"violations_count={len(result.violations)}\n")
                f.write(f"report_path=logs/privacy_audit_report.md\n")

            # Create annotations for violations
            for v in result.violations:
                level = "error" if v.severity == ViolationSeverity.HIGH else "warning"
                print(f"::{level}::Privacy violation at {v.endpoint}: {v.message}")

        # Determine exit code
        if result.violations:
            high_severity = [v for v in result.violations if v.severity == ViolationSeverity.HIGH]
            if high_severity or args.fail_fast:
                return ExitCode.PRIVACY_VIOLATION

        return ExitCode.SUCCESS

    except Exception as e:
        print(f"::error::Privacy audit failed: {e}")
        return ExitCode.SETUP_ERROR


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
