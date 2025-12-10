#!/usr/bin/env python3
"""
Load Test Results Parser and Analyzer.

Parses Locust CSV output and provides:
- Summary reports
- Pass/fail verdicts based on thresholds
- Historical comparison
- CI-friendly exit codes

Usage:
    # Basic summary
    python parse_load_results.py results_stats.csv

    # Check against thresholds (returns exit code 0=pass, 1=fail)
    python parse_load_results.py results_stats.csv --check-thresholds

    # Save to history and compare with last run
    python parse_load_results.py results_stats.csv --save-history --compare-last

    # Use CI smoke thresholds (stricter)
    python parse_load_results.py results_stats.csv --check-thresholds --ci-mode

    # JSON output for scripting
    python parse_load_results.py results_stats.csv --json

    # Add custom label
    python parse_load_results.py results_stats.csv --label "100_users_5rps"
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

# Import thresholds from config
try:
    from thresholds import (
        CI_SMOKE_THRESHOLDS,
        MAX_FAILURE_RATE,
        RESPONSE_TIME_THRESHOLDS,
    )
except ImportError:
    # Fallback if run from different directory
    sys.path.insert(0, str(Path(__file__).parent))
    from thresholds import (
        CI_SMOKE_THRESHOLDS,
        MAX_FAILURE_RATE,
        RESPONSE_TIME_THRESHOLDS,
    )

# History file location
HISTORY_FILE = Path(__file__).parent / "results" / "load_test_history.json"


@dataclass
class EndpointStats:
    """Statistics for a single endpoint."""

    name: str
    request_type: str
    request_count: int
    failure_count: int
    median_ms: float
    avg_ms: float
    min_ms: float
    max_ms: float
    p50: float
    p95: float
    p99: float

    @property
    def failure_rate(self) -> float:
        """Failure rate as percentage."""
        if self.request_count == 0:
            return 0.0
        return (self.failure_count / self.request_count) * 100

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> EndpointStats:
        """Parse a CSV row into EndpointStats."""

        def safe_float(value: str, default: float = 0.0) -> float:
            try:
                return float(value) if value else default
            except (ValueError, TypeError):
                return default

        def safe_int(value: str, default: int = 0) -> int:
            try:
                return int(float(value)) if value else default
            except (ValueError, TypeError):
                return default

        return cls(
            name=row.get("Name", ""),
            request_type=row.get("Type", ""),
            request_count=safe_int(row.get("Request Count", "0")),
            failure_count=safe_int(row.get("Failure Count", "0")),
            median_ms=safe_float(row.get("Median Response Time", "0")),
            avg_ms=safe_float(row.get("Average Response Time", "0")),
            min_ms=safe_float(row.get("Min Response Time", "0")),
            max_ms=safe_float(row.get("Max Response Time", "0")),
            p50=safe_float(row.get("50%", "0")),
            p95=safe_float(row.get("95%", "0")),
            p99=safe_float(row.get("99%", "0")),
        )


@dataclass
class LoadTestResult:
    """Complete load test result."""

    timestamp: str
    label: str
    endpoints: dict[str, EndpointStats] = field(default_factory=dict)
    aggregated: EndpointStats | None = None

    @property
    def total_requests(self) -> int:
        if self.aggregated:
            return self.aggregated.request_count
        return sum(e.request_count for e in self.endpoints.values())

    @property
    def total_failures(self) -> int:
        if self.aggregated:
            return self.aggregated.failure_count
        return sum(e.failure_count for e in self.endpoints.values())

    @property
    def overall_failure_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return (self.total_failures / self.total_requests) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "label": self.label,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "failure_rate": round(self.overall_failure_rate, 2),
            "endpoints": {
                name: {
                    "requests": e.request_count,
                    "failures": e.failure_count,
                    "failure_rate": round(e.failure_rate, 2),
                    "p50": round(e.p50, 1),
                    "p95": round(e.p95, 1),
                    "p99": round(e.p99, 1),
                }
                for name, e in self.endpoints.items()
            },
        }


@dataclass
class ThresholdViolation:
    """A threshold violation."""

    endpoint: str
    metric: str
    threshold: float
    actual: float
    severity: str = "error"  # "error" or "warning"


def parse_stats_csv(csv_path: Path) -> LoadTestResult:
    """Parse a Locust stats CSV file."""
    result = LoadTestResult(
        timestamp=datetime.now().isoformat(),
        label=csv_path.parent.name,
    )

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats = EndpointStats.from_csv_row(row)
            if stats.name == "Aggregated" or not stats.name:
                result.aggregated = stats
            else:
                result.endpoints[stats.name] = stats

    return result


def check_thresholds(
    result: LoadTestResult, ci_mode: bool = False
) -> list[ThresholdViolation]:
    """Check result against thresholds, return violations."""
    violations: list[ThresholdViolation] = []

    # Select thresholds based on mode
    if ci_mode:
        max_failure = CI_SMOKE_THRESHOLDS.get("max_failure_rate", 0.0)
        thresholds = CI_SMOKE_THRESHOLDS
    else:
        max_failure = MAX_FAILURE_RATE
        thresholds = RESPONSE_TIME_THRESHOLDS

    # Check overall failure rate
    if result.overall_failure_rate > max_failure:
        violations.append(
            ThresholdViolation(
                endpoint="overall",
                metric="failure_rate",
                threshold=max_failure,
                actual=result.overall_failure_rate,
            )
        )

    # Check endpoint-specific thresholds
    for name, stats in result.endpoints.items():
        endpoint_thresholds = thresholds.get(name, {})

        # P95 check
        p95_max = endpoint_thresholds.get("p95_max")
        if p95_max and stats.p95 > p95_max:
            violations.append(
                ThresholdViolation(
                    endpoint=name,
                    metric="p95",
                    threshold=p95_max,
                    actual=stats.p95,
                )
            )

        # P50 check (if defined)
        p50_max = endpoint_thresholds.get("p50_max")
        if p50_max and stats.p50 > p50_max:
            violations.append(
                ThresholdViolation(
                    endpoint=name,
                    metric="p50",
                    threshold=p50_max,
                    actual=stats.p50,
                    severity="warning",
                )
            )

    return violations


def format_ms(ms: float) -> str:
    """Format milliseconds for display."""
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def print_summary(result: LoadTestResult, violations: list[ThresholdViolation]) -> None:
    """Print a human-readable summary."""
    print("=" * 50)
    print("  Load Test Summary")
    print("=" * 50)
    print(f"Date:     {result.timestamp}")
    print(f"Label:    {result.label}")
    print()

    # Endpoint table
    print("Endpoints:")
    print(f"  {'Name':<16} {'Reqs':>7} {'Fail':>6} {'Rate':>6} {'P50':>8} {'P95':>8}")
    print("  " + "-" * 53)

    for name, stats in sorted(result.endpoints.items()):
        print(
            f"  {name:<16} {stats.request_count:>7} {stats.failure_count:>6} "
            f"{stats.failure_rate:>5.1f}% {format_ms(stats.p50):>8} {format_ms(stats.p95):>8}"
        )

    print()
    print(
        f"Overall: {result.total_requests} requests, "
        f"{result.total_failures} failures ({result.overall_failure_rate:.2f}%)"
    )
    print()

    # Verdict
    if not violations:
        print("Verdict: PASS")
    else:
        errors = [v for v in violations if v.severity == "error"]
        warnings = [v for v in violations if v.severity == "warning"]

        if errors:
            print("Verdict: FAIL")
            print()
            print("Threshold Violations:")
            for v in errors:
                print(
                    f"  [{v.endpoint}] {v.metric}: {v.actual:.1f} > {v.threshold:.1f}"
                )

        if warnings:
            print()
            print("Warnings:")
            for v in warnings:
                print(
                    f"  [{v.endpoint}] {v.metric}: {v.actual:.1f} > {v.threshold:.1f}"
                )

    print("=" * 50)


def load_history() -> list[dict[str, Any]]:
    """Load historical results."""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_to_history(result: LoadTestResult) -> None:
    """Save result to history file."""
    history = load_history()
    history.append(result.to_dict())

    # Keep last 100 results
    if len(history) > 100:
        history = history[-100:]

    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

    print(f"Saved to history: {HISTORY_FILE}")


def compare_with_last(result: LoadTestResult) -> None:
    """Compare current result with the last historical result."""
    history = load_history()
    if len(history) < 2:
        print("Not enough history for comparison (need at least 2 runs)")
        return

    # Get the second-to-last (previous run, since current is already appended)
    previous = history[-2]

    print()
    print("=" * 50)
    print("  Comparison vs Last Run")
    print("=" * 50)
    print(f"  {'Metric':<20} {'Previous':>12} {'Current':>12} {'Change':>10}")
    print("  " + "-" * 54)

    # Compare failure rate
    prev_rate = previous.get("failure_rate", 0)
    curr_rate = result.overall_failure_rate
    change = curr_rate - prev_rate
    indicator = "" if change == 0 else ("" if change < 0 else "")
    print(f"  {'failure_rate':<20} {prev_rate:>11.2f}% {curr_rate:>11.2f}% {change:>+9.2f}% {indicator}")

    # Compare key endpoints
    prev_endpoints = previous.get("endpoints", {})
    for name in ["login", "send_message", "ttfe", "e2e_full_latency"]:
        if name in result.endpoints and name in prev_endpoints:
            prev_p95 = prev_endpoints[name].get("p95", 0)
            curr_p95 = result.endpoints[name].p95

            if prev_p95 > 0:
                pct_change = ((curr_p95 - prev_p95) / prev_p95) * 100
                indicator = "" if pct_change <= 0 else ""
                print(
                    f"  {name + '_p95':<20} {format_ms(prev_p95):>12} {format_ms(curr_p95):>12} {pct_change:>+9.1f}% {indicator}"
                )

    print("=" * 50)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Parse and analyze Locust load test results"
    )
    parser.add_argument("csv_file", type=Path, help="Path to results_stats.csv")
    parser.add_argument(
        "--check-thresholds",
        action="store_true",
        help="Check against thresholds and set exit code",
    )
    parser.add_argument(
        "--ci-mode",
        action="store_true",
        help="Use stricter CI smoke test thresholds",
    )
    parser.add_argument(
        "--save-history",
        action="store_true",
        help="Save results to history file",
    )
    parser.add_argument(
        "--compare-last",
        action="store_true",
        help="Compare with last historical run",
    )
    parser.add_argument(
        "--label",
        type=str,
        default="",
        help="Custom label for this run",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of human-readable",
    )

    args = parser.parse_args()

    # Validate input
    if not args.csv_file.exists():
        print(f"Error: File not found: {args.csv_file}", file=sys.stderr)
        return 1

    # Parse results
    result = parse_stats_csv(args.csv_file)
    if args.label:
        result.label = args.label

    # Check thresholds
    violations = check_thresholds(result, ci_mode=args.ci_mode)

    # Output
    if args.json:
        output = result.to_dict()
        output["violations"] = [
            {
                "endpoint": v.endpoint,
                "metric": v.metric,
                "threshold": v.threshold,
                "actual": v.actual,
                "severity": v.severity,
            }
            for v in violations
        ]
        output["passed"] = len([v for v in violations if v.severity == "error"]) == 0
        print(json.dumps(output, indent=2))
    else:
        print_summary(result, violations)

    # Save to history
    if args.save_history:
        save_to_history(result)

    # Compare with last
    if args.compare_last:
        compare_with_last(result)

    # Exit code for CI
    if args.check_thresholds:
        errors = [v for v in violations if v.severity == "error"]
        return 1 if errors else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
