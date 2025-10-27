#!/usr/bin/env bash
set -euo pipefail

BACKEND_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.."; pwd)"
cd "$BACKEND_ROOT"

pytest --confcutdir=tests/perf tests/perf/test_perf_counters_headers.py -q
