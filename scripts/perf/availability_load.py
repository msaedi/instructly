#!/usr/bin/env python3
"""
Async tail-latency load generator for availability GET/SAVE mix.

Usage (load run):
    python scripts/perf/availability_load.py \
        --api-base http://localhost:8000 \
        --token "$TOKEN" \
        --instructor "$INSTR_ID" \
        --week-start 2025-11-10 \
        --users 5 \
        --minutes 3

Usage (summaries/charts from existing CSVs):
    python scripts/perf/availability_load.py \
        --summaries scripts/perf/out/availability_load_1u_2m_*.csv \
        --chart-dir docs/perf/img
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import dataclasses
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, List, Optional

import httpx

DEFAULT_OUTPUT_DIR = Path("scripts/perf/out")
DEFAULT_IMG_DIR = Path("docs/perf/img")


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #


@dataclasses.dataclass(slots=True)
class RequestRecord:
    """Single HTTP request result from the load test."""

    ts_start: str
    users: int
    user_id: int
    method: str
    path: str
    status: int
    latency_ms: float
    db_query_count: int
    db_table_availability_slots: int
    cache_hits: int
    cache_misses: int
    db_sql_samples: int
    mix_get: int
    mix_save: int
    save_interval: float
    debug_sql: bool

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def pct(values: List[float], percentile: float) -> float:
    """Nearest-rank percentile."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    rank = max(0, min(len(sorted_vals) - 1, math.ceil(percentile / 100 * len(sorted_vals)) - 1))
    return sorted_vals[rank]


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_mix(value: str) -> tuple[int, int]:
    try:
        get_part, save_part = value.split(",")
        get_ratio = int(get_part)
        save_ratio = int(save_part)
        if get_ratio <= 0 or save_ratio < 0:
            raise ValueError
        return get_ratio, save_ratio
    except Exception as exc:  # pragma: no cover - defensive
        raise argparse.ArgumentTypeError(f"Invalid mix '{value}'. Expected '80,20'.") from exc


def iso_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_save_payload(week_start: str, slot_hour: int, minute_offset: int = 0) -> dict[str, Any]:
    """Construct minimal week payload mutating the Monday slot."""
    monday = datetime.fromisoformat(week_start)
    monday_date = monday.date()
    schedule = [
        {
            "date": monday_date.isoformat(),
            "start_time": f"{slot_hour:02d}:{minute_offset:02d}",
            "end_time": f"{slot_hour + 1:02d}:{minute_offset:02d}",
        }
    ]
    return {
        "week_start": monday_date.isoformat(),
        "clear_existing": False,
        "schedule": schedule,
    }


# --------------------------------------------------------------------------- #
# Load execution
# --------------------------------------------------------------------------- #


class LoadRunner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.mix_get, self.mix_save = parse_mix(args.mix)
        self.total_ratio = self.mix_get + self.mix_save
        self.records: list[RequestRecord] = []
        self.save_interval = args.save_interval
        self.debug_sql = args.debug_sql
        self.week_start = args.week_start
        self.session: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "LoadRunner":
        headers = {
            "Authorization": f"Bearer {self.args.token}",
            "Content-Type": "application/json",
        }
        if self.debug_sql:
            headers["x-debug-sql"] = "1"
        timeout = httpx.Timeout(30.0, connect=5.0, read=30.0, write=30.0)
        self.session = httpx.AsyncClient(base_url=self.args.api_base, headers=headers, timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.session:
            await self.session.aclose()

    async def run(self) -> tuple[list[RequestRecord], Path]:
        assert self.session is not None
        warmup_seconds = self.args.warmup_seconds
        duration_seconds = self.args.minutes * 60
        warmup_end = asyncio.get_event_loop().time() + warmup_seconds
        test_end = warmup_end + duration_seconds

        tasks = []
        for user_id in range(1, self.args.users + 1):
            tasks.append(
                asyncio.create_task(
                    self.worker(user_id=user_id, warmup_end=warmup_end, test_end=test_end)
                )
            )

        await asyncio.gather(*tasks)

        output_path = self._write_csv()
        summary = compute_summary(self.records)
        summary_path = output_path.with_suffix(".summary.json")
        summary_path.write_text(json.dumps(summary, indent=2))
        print_summary(summary)
        return self.records, output_path

    async def worker(self, user_id: int, warmup_end: float, test_end: float) -> None:
        assert self.session is not None
        last_save = 0.0
        save_counter = 0
        await asyncio.sleep(random.uniform(0, 0.3))

        while asyncio.get_event_loop().time() < test_end:
            now = asyncio.get_event_loop().time()
            in_warmup = now < warmup_end
            action = self._choose_action(now, last_save)

            try:
                if action == "GET":
                    record = await self._perform_get(user_id, record=not in_warmup)
                else:
                    record = await self._perform_save(
                        user_id,
                        record=not in_warmup,
                        slot_hour=10 + (save_counter % 2),
                        minute_offset=(save_counter * 5) % 45,
                    )
                    last_save = now
                    save_counter += 1
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[worker {user_id}] error: {exc}", file=sys.stderr)
                await asyncio.sleep(0.5)
                continue

            if record is not None:
                self.records.append(record)

            await asyncio.sleep(random.uniform(0.05, 0.2))

    def _choose_action(self, now: float, last_save: float) -> str:
        if self.mix_save == 0:
            return "GET"
        if now - last_save < self.save_interval:
            return "GET"
        choice = random.randint(1, self.total_ratio)
        return "GET" if choice <= self.mix_get else "SAVE"

    async def _perform_get(self, user_id: int, record: bool) -> Optional[RequestRecord]:
        assert self.session is not None
        params = {"start_date": self.week_start}
        return await self._send_request(
            user_id=user_id,
            method="GET",
            url="/instructors/availability/week",
            json_payload=None,
            params=params,
            record=record,
        )

    async def _perform_save(
        self,
        user_id: int,
        record: bool,
        slot_hour: int,
        minute_offset: int,
    ) -> Optional[RequestRecord]:
        assert self.session is not None
        payload = build_save_payload(self.week_start, slot_hour, minute_offset)
        return await self._send_request(
            user_id=user_id,
            method="POST",
            url="/instructors/availability/week",
            json_payload=payload,
            params=None,
            record=record,
        )

    async def _send_request(
        self,
        user_id: int,
        method: str,
        url: str,
        json_payload: Optional[dict[str, Any]],
        params: Optional[dict[str, Any]],
        record: bool,
    ) -> Optional[RequestRecord]:
        assert self.session is not None
        ts_start = iso_timestamp()
        start = asyncio.get_event_loop().time()
        try:
            response = await self.session.request(method, url, json=json_payload, params=params)
        except httpx.HTTPError as exc:
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000.0
            if record:
                self.records.append(
                    RequestRecord(
                        ts_start=ts_start,
                        users=self.args.users,
                        user_id=user_id,
                        method=method,
                        path=url,
                        status=0,
                        latency_ms=latency_ms,
                        db_query_count=0,
                        db_table_availability_slots=0,
                        cache_hits=0,
                        cache_misses=0,
                        db_sql_samples=0,
                        mix_get=self.mix_get,
                        mix_save=self.mix_save,
                        save_interval=self.save_interval,
                        debug_sql=self.debug_sql,
                    )
                )
            raise exc

        latency_ms = (asyncio.get_event_loop().time() - start) * 1000.0

        if not record:
            return None

        headers = response.headers
        return RequestRecord(
            ts_start=ts_start,
            users=self.args.users,
            user_id=user_id,
            method=method,
            path=url,
            status=response.status_code,
            latency_ms=latency_ms,
            db_query_count=int(headers.get("x-db-query-count", "0") or 0),
            db_table_availability_slots=int(headers.get("x-db-table-availability_slots", "0") or 0),
            cache_hits=int(headers.get("x-cache-hits", "0") or 0),
            cache_misses=int(headers.get("x-cache-misses", "0") or 0),
            db_sql_samples=int(headers.get("x-db-sql-samples", "0") or 0),
            mix_get=self.mix_get,
            mix_save=self.mix_save,
            save_interval=self.save_interval,
            debug_sql=self.debug_sql,
        )

    def _write_csv(self) -> Path:
        ensure_dir(DEFAULT_OUTPUT_DIR)
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M")
        filename = (
            f"availability_load_{self.args.users}u_{self.args.minutes}m_{timestamp}.csv"
        )
        output_path = DEFAULT_OUTPUT_DIR / filename
        fieldnames = [
            "ts_start",
            "users",
            "user_id",
            "method",
            "path",
            "status",
            "latency_ms",
            "db_query_count",
            "db_table_availability_slots",
            "cache_hits",
            "cache_misses",
            "db_sql_samples",
            "mix_get",
            "mix_save",
            "save_interval",
            "debug_sql",
        ]
        with output_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for record in self.records:
                writer.writerow(record.to_dict())
        print(f"Wrote {output_path}")
        return output_path


# --------------------------------------------------------------------------- #
# Summary & charts
# --------------------------------------------------------------------------- #


def compute_summary(records: Iterable[RequestRecord | dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for rec in records:
        if isinstance(rec, RequestRecord):
            rows.append(rec.to_dict())
        else:
            rows.append(rec)

    if not rows:
        return {}

    users = rows[0].get("users", 0)
    mix_get = rows[0].get("mix_get", 0)
    mix_save = rows[0].get("mix_save", 0)

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[row["method"]].append(row)
        buckets["ALL"].append(row)

    summary: dict[str, Any] = {
        "users": users,
        "mix": {"GET": mix_get, "SAVE": mix_save},
        "methods": {},
    }

    for method, items in buckets.items():
        latencies = [float(item["latency_ms"]) for item in items]
        db_counts = [int(item["db_query_count"]) for item in items]
        cache_hits = [int(item["cache_hits"]) for item in items]
        cache_misses = [int(item["cache_misses"]) for item in items]
        errors = [item for item in items if int(item["status"]) >= 400 or int(item["status"]) == 0]
        summary["methods"][method] = {
            "count": len(items),
            "p50_ms": pct(latencies, 50),
            "p95_ms": pct(latencies, 95),
            "p99_ms": pct(latencies, 99),
            "avg_latency_ms": statistics.fmean(latencies) if latencies else 0.0,
            "avg_db_queries": statistics.fmean(db_counts) if db_counts else 0.0,
            "p95_db_queries": pct(db_counts, 95) if db_counts else 0.0,
            "avg_cache_hits": statistics.fmean(cache_hits) if cache_hits else 0.0,
            "p95_cache_hits": pct(cache_hits, 95) if cache_hits else 0.0,
            "avg_cache_misses": statistics.fmean(cache_misses) if cache_misses else 0.0,
            "p95_cache_misses": pct(cache_misses, 95) if cache_misses else 0.0,
            "error_rate": len(errors) / len(items) if items else 0.0,
        }

    return summary


def print_summary(summary: dict[str, Any]) -> None:
    if not summary:
        print("No data to summarise.")
        return

    users = summary.get("users")
    mix = summary.get("mix", {})
    print("\n=== Availability Load Summary ===")
    print(f"Users: {users} | Mix GET:{mix.get('GET')} SAVE:{mix.get('SAVE')}")
    for method, data in summary["methods"].items():
        print(f"\n[{method}] count={data['count']} error_rate={data['error_rate']:.2%}")
        print(
            f"  Latency p50/p95/p99: {data['p50_ms']:.1f} / {data['p95_ms']:.1f} / {data['p99_ms']:.1f} ms"
        )
        print(
            f"  DB queries avg/p95: {data['avg_db_queries']:.2f} / {data['p95_db_queries']:.1f}"
        )
        print(
            f"  Cache hits avg/p95: {data['avg_cache_hits']:.2f} / {data['p95_cache_hits']:.1f}"
        )
        print(
            f"  Cache misses avg/p95: {data['avg_cache_misses']:.2f} / {data['p95_cache_misses']:.1f}"
        )
    print("")


def load_csv_records(path: Path) -> list[dict[str, Any]]:
    with path.open() as f:
        reader = csv.DictReader(f)
        return [row for row in reader]


def summarise_files(paths: list[Path], chart_dir: Optional[Path]) -> None:
    summaries = []
    for path in paths:
        if path.suffix.lower() != ".csv":
            print(f"Skipping non-CSV summary source: {path}")
            continue
        rows = load_csv_records(path)
        clipped_rows = rows[:50000]
        if len(rows) > len(clipped_rows):
            print(f"  ⚠️  {path} has {len(rows)} rows; summarising first {len(clipped_rows)}.")
        summary = compute_summary(clipped_rows)
        summary["source"] = str(path)
        summaries.append(summary)
        print(f"Summary for {path}:")
        print_summary(summary)

    if chart_dir:
        generate_charts(summaries, chart_dir)


def generate_charts(summaries: list[dict[str, Any]], chart_dir: Path) -> None:
    ensure_dir(chart_dir)
    try:
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover - optional
        print("matplotlib not available; skipping chart generation.")
        return

    by_users: dict[int, dict[str, Any]] = {}
    for summary in summaries:
        if not summary:
            continue
        users = summary.get("users")
        overall = summary["methods"].get("ALL", {})
        if users:
            by_users[users] = overall

    if not by_users:
        print("No summaries with user data for chart generation.")
        return

    sorted_users = sorted(by_users.keys())
    p50 = [by_users[u].get("p50_ms", 0) for u in sorted_users]
    p95 = [by_users[u].get("p95_ms", 0) for u in sorted_users]
    p99 = [by_users[u].get("p99_ms", 0) for u in sorted_users]

    width = 0.25
    x_positions = list(range(len(sorted_users)))

    plt.figure(figsize=(8, 4))
    plt.bar([x - width for x in x_positions], p50, width=width, label="p50")
    plt.bar(x_positions, p95, width=width, label="p95")
    plt.bar([x + width for x in x_positions], p99, width=width, label="p99")
    plt.xticks(x_positions, [str(u) for u in sorted_users])
    plt.xlabel("Concurrent users")
    plt.ylabel("Latency (ms)")
    plt.title("Availability latency percentiles")
    plt.legend()
    latency_chart = chart_dir / "availability_tail_latency.png"
    plt.tight_layout()
    plt.savefig(latency_chart, dpi=160)
    plt.close()
    print(f"Wrote {latency_chart}")

    # Optional histogram for worst tail
    worst_users = max(sorted_users, key=lambda u: by_users[u].get("p99_ms", 0))
    worst_summary = next(
        (summary for summary in summaries if summary.get("users") == worst_users), None
    )
    if worst_summary:
        csv_path = Path(worst_summary.get("source", ""))
        if csv_path.exists():
            rows = load_csv_records(csv_path)
            latencies = [float(row["latency_ms"]) for row in rows]
            plt.figure(figsize=(8, 4))
            plt.hist(latencies, bins=30, color="#4a90e2", alpha=0.8)
            plt.xlabel("Latency (ms)")
            plt.ylabel("Request count")
            plt.title(f"Latency distribution (users={worst_users})")
            histogram_path = chart_dir / f"availability_latency_hist_{worst_users}u.png"
            plt.tight_layout()
            plt.savefig(histogram_path, dpi=160)
            plt.close()
            print(f"Wrote {histogram_path}")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Availability GET/SAVE load generator.")
    parser.add_argument("--api-base", type=str, help="API base URL, e.g. http://localhost:8000")
    parser.add_argument("--token", type=str, help="Bearer token for requests")
    parser.add_argument("--instructor", type=str, help="Instructor ID to target")
    parser.add_argument("--week-start", type=str, help="Week start date (YYYY-MM-DD)")
    parser.add_argument("--users", type=int, default=1, help="Concurrent users (default 1)")
    parser.add_argument("--minutes", type=int, default=2, help="Duration in minutes")
    parser.add_argument("--mix", type=str, default="80,20", help="Traffic mix GET,SAVE (default 80,20)")
    parser.add_argument(
        "--warmup-seconds", type=int, default=10, help="Warmup duration before recording results"
    )
    parser.add_argument(
        "--save-interval",
        type=float,
        default=7.5,
        help="Minimum seconds between SAVE calls per user (default 7.5)",
    )
    parser.add_argument(
        "--debug-sql",
        action="store_true",
        help="Include x-debug-sql header to capture SQL samples.",
    )
    parser.add_argument(
        "--summaries",
        nargs="*",
        help="If provided, skip load run and summarise the given CSV files (glob allowed).",
    )
    parser.add_argument(
        "--chart-dir",
        type=str,
        default=str(DEFAULT_IMG_DIR),
        help="Directory for summary charts (default docs/perf/img).",
    )

    args = parser.parse_args(argv)

    if args.summaries:
        # Summaries mode: allow glob patterns
        paths: list[Path] = []
        for pattern in args.summaries:
            expanded = list(map(Path, sorted(Path().glob(pattern))))
            if expanded:
                paths.extend(expanded)
            else:
                paths.append(Path(pattern))
        args.summaries = paths
        return args

    # Load run mode: ensure required fields are present
    for field in ("api_base", "token", "instructor", "week_start"):
        if getattr(args, field) in (None, ""):
            parser.error(f"--{field.replace('_', '-')} is required for load run.")

    return args


def main(argv: Optional[list[str]] = None) -> None:
    args = parse_args(argv)
    if args.summaries:
        chart_dir = Path(args.chart_dir) if args.chart_dir else None
        summarise_files(args.summaries, chart_dir)
        return

    asyncio.run(run_load(args))


async def run_load(args: argparse.Namespace) -> None:
    async with LoadRunner(args) as runner:
        await runner.run()


if __name__ == "__main__":
    main()
