#!/usr/bin/env python3
"""Availability baseline harness for instructor availability endpoints.

Usage:
    python scripts/perf/availability_baseline.py \
        --api-base http://localhost:8000 \
        --instructor-id <UUID> \
        --week-start 2024-11-18 \
        --week-payload-file scripts/perf/sample_week_payload.json \
        --auth-token <JWT>

Requirements:
    * Backend devserver running with AVAILABILITY_PERF_DEBUG=1 so spans are emitted.
    * Target instructor must exist with relevant availability data.
    * The payload file should contain a WeekSpecificScheduleCreate-compatible JSON body.

Outputs:
    * CSV latency samples under scripts/perf/out/availability_<endpoint>_<YYYYMMDD>.csv
    * p50/p95/p99 charts under docs/perf/img/availability_<endpoint>_<YYYYMMDD>.png
    * Console summary with cold vs warm latency percentiles.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import httpx

try:  # Lazy optional dependency for chart generation
    import matplotlib.pyplot as plt  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    plt = None  # type: ignore


LOGGER = logging.getLogger("availability.perf")


@dataclass
class Sample:
    """Single latency measurement."""

    timestamp: str
    endpoint: str
    slug: str
    method: str
    path: str
    phase: str
    iteration: int
    latency_ms: float
    status_code: int
    payload_bytes: Optional[int]
    response_bytes: Optional[int]
    error: Optional[str]


@dataclass
class EndpointResult:
    slug: str
    name: str
    samples: List[Sample]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure availability endpoint latencies")
    parser.add_argument("--api-base", required=True, help="Base URL of the API, e.g. http://localhost:8000")
    parser.add_argument("--instructor-id", required=True, help="Instructor UUID to exercise")
    parser.add_argument("--week-start", required=True, type=_parse_date, help="Monday ISO date (YYYY-MM-DD)")
    parser.add_argument(
        "--copy-target-week",
        type=_parse_date,
        help="Target Monday for copy-week (defaults to week_start + 7 days)",
    )
    parser.add_argument(
        "--week-payload-file",
        required=True,
        help="Path to JSON payload for POST /instructors/availability/week",
    )
    parser.add_argument("--repetitions", type=int, default=5, help="Total calls per endpoint (>=1)")
    parser.add_argument("--auth-token", help="Bearer token for Authorization header")
    parser.add_argument(
        "--auth-header",
        default="Authorization",
        help="Header name to carry the auth token (default Authorization)",
    )
    parser.add_argument(
        "--auth-prefix",
        default="Bearer",
        help="Prefix applied before the token value (default Bearer)",
    )
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        help="Additional header in KEY:VALUE form (may be supplied multiple times)",
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="Per-request timeout in seconds")
    parser.add_argument("--output-dir", default="scripts/perf/out", help="Directory for CSV outputs")
    parser.add_argument("--img-dir", default="docs/perf/img", help="Directory for chart images")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def _parse_date(value: str) -> date:
    try:
        return datetime.fromisoformat(value).date()
    except ValueError as exc:  # pragma: no cover - CLI safeguard
        raise argparse.ArgumentTypeError(f"Invalid date '{value}': {exc}") from exc


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def load_payload(path: Path, week_start: date) -> Dict[str, Any]:
    data = json.loads(path.read_text())
    data["week_start"] = week_start.isoformat()
    return data


def build_headers(args: argparse.Namespace) -> Dict[str, str]:
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if args.auth_token:
        token_value = args.auth_token if not args.auth_prefix else f"{args.auth_prefix} {args.auth_token}".strip()
        headers[args.auth_header] = token_value
    for raw in args.header:
        if ":" not in raw:
            LOGGER.warning("Ignoring malformed header '%s'", raw)
            continue
        key, value = raw.split(":", 1)
        headers[key.strip()] = value.strip()
    return headers


def clone_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return json.loads(json.dumps(payload))


def percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    sorted_vals = sorted(values)
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (pct / 100.0) * (len(sorted_vals) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    d0 = sorted_vals[f] * (c - k)
    d1 = sorted_vals[c] * (k - f)
    return d0 + d1


def measure_request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    timeout: float,
) -> Tuple[float, int, Optional[int], Optional[str]]:
    start = time.perf_counter()
    status_code = -1
    resp_bytes: Optional[int] = None
    error: Optional[str] = None
    try:
        response = client.request(method, path, params=params, json=json_body, timeout=timeout)
        status_code = response.status_code
        resp_bytes = len(response.content or b"")
    except httpx.HTTPError as exc:
        error = str(exc)
        response = getattr(exc, "response", None)
        if response is not None:
            status_code = response.status_code
            resp_bytes = len(response.content or b"")
    latency_ms = (time.perf_counter() - start) * 1000.0
    if error:
        LOGGER.warning("%s %s failed: %s", method, path, error)
    return latency_ms, status_code, resp_bytes, error


def run_endpoint(
    *,
    client: httpx.Client,
    slug: str,
    name: str,
    method: str,
    path: str,
    repetitions: int,
    timeout: float,
    params: Optional[Dict[str, Any]] = None,
    json_body: Optional[Dict[str, Any]] = None,
) -> EndpointResult:
    LOGGER.info("Running %s (%s %s) with %s calls", name, method, path, repetitions)
    samples: List[Sample] = []
    for iteration in range(repetitions):
        phase = "cold" if iteration == 0 else "warm"
        payload = clone_payload(json_body) if json_body is not None else None
        latency_ms, status_code, resp_bytes, error = measure_request(
            client,
            method,
            path,
            params=params,
            json_body=payload,
            timeout=timeout,
        )
        payload_bytes = len(json.dumps(payload).encode("utf-8")) if payload is not None else 0
        samples.append(
            Sample(
                timestamp=datetime.utcnow().isoformat(),
                endpoint=name,
                slug=slug,
                method=method,
                path=path,
                phase=phase,
                iteration=iteration + 1,
                latency_ms=round(latency_ms, 3),
                status_code=status_code,
                payload_bytes=payload_bytes,
                response_bytes=resp_bytes,
                error=error,
            )
        )
    return EndpointResult(slug=slug, name=name, samples=samples)


def write_csv(result: EndpointResult, output_dir: Path, date_tag: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / f"availability_{result.slug}_{date_tag}.csv"
    with csv_path.open("w", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "timestamp",
                "endpoint",
                "method",
                "path",
                "phase",
                "iteration",
                "latency_ms",
                "status_code",
                "payload_bytes",
                "response_bytes",
                "error",
            ]
        )
        for sample in result.samples:
            writer.writerow(
                [
                    sample.timestamp,
                    sample.endpoint,
                    sample.method,
                    sample.path,
                    sample.phase,
                    sample.iteration,
                    sample.latency_ms,
                    sample.status_code,
                    sample.payload_bytes,
                    sample.response_bytes,
                    sample.error or "",
                ]
            )
    LOGGER.info("Wrote %s samples to %s", len(result.samples), csv_path)
    return csv_path


def compute_stats(samples: Iterable[Sample]) -> Dict[str, Dict[str, Optional[float]]]:
    grouped: Dict[str, List[float]] = {"cold": [], "warm": []}
    for sample in samples:
        grouped.setdefault(sample.phase, []).append(sample.latency_ms)
    stats: Dict[str, Dict[str, Optional[float]]] = {}
    for phase, values in grouped.items():
        if not values:
            continue
        stats[phase] = {
            "count": float(len(values)),
            "mean": sum(values) / len(values),
            "p50": percentile(values, 50),
            "p95": percentile(values, 95),
            "p99": percentile(values, 99),
        }
    return stats


def render_chart(result: EndpointResult, stats: Dict[str, Dict[str, Optional[float]]], img_dir: Path, date_tag: str) -> Optional[Path]:
    if plt is None:
        LOGGER.warning("matplotlib not installed; skipping chart for %s", result.name)
        return None
    if "warm" not in stats and "cold" not in stats:
        return None
    img_dir.mkdir(parents=True, exist_ok=True)
    metrics = ["p50", "p95", "p99"]
    cold_values = [stats.get("cold", {}).get(metric) or 0 for metric in metrics]
    warm_values = [stats.get("warm", {}).get(metric) or 0 for metric in metrics]
    x = range(len(metrics))
    bar_width = 0.35
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar([i - bar_width / 2 for i in x], cold_values, bar_width, label="cold")
    ax.bar([i + bar_width / 2 for i in x], warm_values, bar_width, label="warm")
    ax.set_ylabel("Latency (ms)")
    ax.set_title(f"{result.name} latency percentiles")
    ax.set_xticks(list(x))
    ax.set_xticklabels(metrics)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    img_path = img_dir / f"availability_{result.slug}_{date_tag}.png"
    fig.tight_layout()
    fig.savefig(img_path)
    plt.close(fig)
    LOGGER.info("Wrote chart %s", img_path)
    return img_path


def summarize(result: EndpointResult, stats: Dict[str, Dict[str, Optional[float]]]) -> None:
    LOGGER.info("Summary for %s", result.name)
    for phase in ("cold", "warm"):
        if phase not in stats:
            continue
        phase_stats = stats[phase]
        LOGGER.info(
            "  %-4s -> count=%d mean=%.2fms p50=%.2fms p95=%.2fms p99=%.2fms",
            phase,
            int(phase_stats["count"] or 0),
            phase_stats["mean"] or 0,
            phase_stats["p50"] or 0,
            phase_stats["p95"] or 0,
            phase_stats["p99"] or 0,
        )


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)

    if args.repetitions < 1:
        LOGGER.error("Repetitions must be >= 1")
        return 1

    week_start = args.week_start
    copy_target = args.copy_target_week or (week_start + timedelta(days=7))
    payload_path = Path(args.week_payload_file)
    if not payload_path.exists():
        LOGGER.error("Payload file %s does not exist", payload_path)
        return 1

    week_payload = load_payload(payload_path, week_start)
    headers = build_headers(args)

    base_url = args.api_base.rstrip("/")
    output_dir = Path(args.output_dir)
    img_dir = Path(args.img_dir)
    date_tag = week_start.strftime("%Y%m%d")

    endpoints: List[EndpointResult] = []

    with httpx.Client(base_url=base_url, headers=headers) as client:
        endpoints.append(
            run_endpoint(
                client=client,
                slug="week_get",
                name="GET /instructors/availability/week",
                method="GET",
                path="/instructors/availability/week",
                repetitions=args.repetitions,
                timeout=args.timeout,
                params={"start_date": week_start.isoformat()},
            )
        )

        endpoints.append(
            run_endpoint(
                client=client,
                slug="week_save",
                name="POST /instructors/availability/week",
                method="POST",
                path="/instructors/availability/week",
                repetitions=args.repetitions,
                timeout=args.timeout,
                json_body=week_payload,
            )
        )

        endpoints.append(
            run_endpoint(
                client=client,
                slug="copy_week",
                name="POST /instructors/availability/copy-week",
                method="POST",
                path="/instructors/availability/copy-week",
                repetitions=args.repetitions,
                timeout=args.timeout,
                json_body={
                    "from_week_start": week_start.isoformat(),
                    "to_week_start": copy_target.isoformat(),
                },
            )
        )

    for result in endpoints:
        csv_path = write_csv(result, output_dir, date_tag)
        stats = compute_stats(result.samples)
        summarize(result, stats)
        render_chart(result, stats, img_dir, date_tag)
        LOGGER.debug("Artifacts for %s stored at %s", result.name, csv_path)

    LOGGER.info("Completed availability baseline run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
