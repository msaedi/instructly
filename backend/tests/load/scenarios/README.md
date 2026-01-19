# Load Test Scenarios

This directory contains standardized load test scenarios for the InstaInstru messaging system.

## Overview

| Scenario | Purpose | Users | Duration | When to Use |
|----------|---------|-------|----------|-------------|
| **S0: Smoke** | Baseline sanity check | 10 | 5 min | Before any deployment, after changes |
| **S1: Capacity** | Find SSE connection limits | 50-400 | 5 min × 5 | Capacity planning, infrastructure sizing |
| **S2: Throughput** | Latency vs message rate | 100 | 5 min × 5 | Performance tuning, SLA definition |
| **S3: Burst** | Redis fan-out stress test | 250 | 5 min | Pre-launch, after Redis changes |
| **S4: Soak** | Long-term stability | 150 | 1-4 hours | Memory leak detection, reliability |

## Prerequisites

### 1. Test Users Seeded
The following users must exist in the preview database:
- `sarah.chen@example.com`
- `emma.johnson@example.com`

Both must have password `Test1234` and be seeded via `prep_db.py`.

### 2. Conversation Configured
The file `config/conversations.json` must map both users to a shared conversation:
```json
{
  "sarah.chen@example.com": { "conversation_id": "...", "booking_id": "..." },
  "emma.johnson@example.com": { "conversation_id": "...", "booking_id": "..." }
}
```

### 3. Infrastructure Running
- Preview backend deployed and healthy
- Redis Pub/Sub operational
- SSE endpoint responding

### 4. Dependencies Installed
```bash
cd backend
source venv/bin/activate
pip install -r requirements-dev.txt  # Includes locust, sseclient-py
```

## Quick Start

```bash
cd backend/tests/load/scenarios

# Make scripts executable (one-time)
chmod +x *.sh

# Run smoke test first
./s0_smoke.sh

# Then capacity sweep
./s1_capacity.sh

# Then throughput analysis
./s2_throughput.sh
```

## Scenario Details

### S0: Smoke / Baseline
**Purpose**: Quick sanity check to verify the system works and establish baseline metrics.

```bash
./s0_smoke.sh
```

**Parameters**:
- Users: 10
- Ramp: 2 users/sec
- Duration: 5 minutes

**Success Criteria**:
- 0% error rate
- `e2e_full_latency` P95 < 500ms
- `send_message` P95 < 300ms

**Run this**: Before deployments, after infrastructure changes, as a quick health check.

---

### S1: SSE Connection Capacity Sweep
**Purpose**: Find the maximum number of concurrent SSE connections before degradation.

```bash
./s1_capacity.sh

# Custom user counts
USER_COUNTS="25 50 75 100" ./s1_capacity.sh
```

**Parameters**:
- User counts: 50, 100, 200, 300, 400 (sequential)
- Ramp: 20 users/sec
- Duration: 5 minutes per step
- Cooldown: 30 seconds between steps

**What to Watch**:
- FastAPI CPU > 70% (warning), > 80% (stop)
- FastAPI Memory > 1.6GB (warning), > 1.8GB (stop)
- Connection errors appearing
- Latency spikes

**Output**: Separate results directory for each user count. Compare HTML reports to find the knee point.

---

### S2: Throughput vs Latency
**Purpose**: Understand how message throughput affects end-to-end latency.

```bash
./s2_throughput.sh

# Custom user count (use ~50% of S1 ceiling)
S2_USERS=75 ./s2_throughput.sh
```

**Parameters**:
- Users: 100 (adjust based on S1 results)
- SSE hold times: 30, 20, 15, 10, 5 seconds
- Duration: 5 minutes per step

**Message Rate Approximations**:
| Hold Time | Messages/min/user |
|-----------|------------------|
| 30s | ~2 |
| 20s | ~3 |
| 15s | ~4 |
| 10s | ~6 |
| 5s | ~12 |

**Analysis**: Graph P95 latency vs message rate. The point where latency starts climbing sharply is your throughput ceiling.

---

### S3: Redis Burst Test
**Purpose**: Verify system handles sudden message spikes without dropping connections or messages.

```bash
./s3_burst.sh

# Custom user count
S3_USERS=200 ./s3_burst.sh
```

**Parameters**:
- Users: 250
- Ramp: 25 users/sec (fast)
- SSE hold: 5s (aggressive)
- Duration: 5 minutes

**Warning**: This test creates high Redis load. Monitor closely.

**Success Criteria**:
- Redis CPU < 80%
- No SSE connection drops
- All messages delivered (no `e2e_full_latency` > 5s)

---

### S4: Soak Test
**Purpose**: Detect memory leaks, connection leaks, and long-term stability issues.

```bash
./s4_soak.sh

# Custom duration
S4_DURATION=4h ./s4_soak.sh

# Custom users
S4_USERS=200 S4_DURATION=2h ./s4_soak.sh
```

**Parameters**:
- Users: 150
- Duration: 1 hour (configurable)
- SSE hold: 25s (moderate)

**What to Track**:
1. Memory at start, 30min, 1hr, 2hr, etc.
2. P95 latency trend over time
3. Error rate trend

**Signs of Problems**:
- Memory increasing linearly = memory leak
- P95 latency drifting upward = degradation
- Error rate increasing = connection/resource leak

## Monitoring During Tests

### Render Dashboard
Monitor these metrics in real-time:
- **FastAPI Service**: CPU, Memory, Response time
- **Redis Instance**: CPU, Memory, Active connections

### Locust Console Output
Watch for:
- Error rates (should stay 0% for S0)
- RPS (requests per second)
- Response time percentiles

### Key Thresholds

| Metric | Baseline | Warning | Critical |
|--------|----------|---------|----------|
| `e2e_full_latency` P95 | < 300ms | 500ms | > 1000ms |
| `send_message` P95 | < 300ms | 500ms | > 800ms |
| `sse_stream` errors | 0% | 1% | > 2% |
| `login` errors | 0% | 0.5% | > 1% |

| Resource | Comfortable | Warning | Upgrade |
|----------|-------------|---------|---------|
| FastAPI CPU | < 60% | 70% | 80% |
| FastAPI Memory | < 1.4GB | 1.6GB | 1.8GB |
| Redis CPU | < 50% | 65% | 80% |
| Redis Memory | < 300MB | 400MB | 450MB |

## Results Directory

Test results are saved to `../results/` with timestamped directories:

```
results/
├── s0_smoke_20241207_143052/
│   ├── report.html         # Visual report (open in browser)
│   ├── results_stats.csv   # Summary statistics
│   └── results_stats_history.csv  # Time-series data
├── s1_capacity_20241207_150000/
│   ├── 50_users/
│   ├── 100_users/
│   └── 200_users/
└── ...
```

**Note**: Results directory is git-ignored. Export important results manually.

## Environment Variables

All scenarios support these overrides:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOADTEST_BASE_URL` | https://preview-api.instainstru.com | Target API |
| `LOADTEST_USERS` | sarah.chen@...,emma.johnson@... | Test user emails |
| `LOADTEST_PASSWORD` | Test1234 | Test user password |
| `LOADTEST_SSE_HOLD_SECONDS` | 25 | Time between SSE cycles |

Scenario-specific:
| Variable | Scenario | Description |
|----------|----------|-------------|
| `USER_COUNTS` | S1 | Space-separated user counts |
| `SSE_HOLD_TIMES` | S2 | Space-separated hold times |
| `S2_USERS` | S2 | Override user count |
| `S3_USERS` | S3 | Override user count |
| `S4_USERS` | S4 | Override user count |
| `S4_DURATION` | S4 | Test duration (e.g., `4h`) |

## Interpreting Results

### S0 (Smoke)
- **Pass**: 0 errors, latency within thresholds
- **Fail**: Any errors = investigate before proceeding

### S1 (Capacity)
- Find the user count where metrics first exceed warning thresholds
- Your safe operational ceiling = that count × 0.8

### S2 (Throughput)
- Graph: X = message rate, Y = P95 latency
- The "elbow" is your sustainable throughput limit

### S3 (Burst)
- **Pass**: All messages delivered, no connection drops
- **Fail**: Review Redis metrics, may need larger instance

### S4 (Soak)
- **Pass**: Flat memory trend, stable latency
- **Fail**: Upward trends indicate leaks, file issue for investigation

## Result Analysis Tools

### Parse Load Results

After running any test, analyze results with the parser:

```bash
# Basic summary
python ../parse_load_results.py results/s0_smoke_*/results_stats.csv

# Check against thresholds (CI mode)
python ../parse_load_results.py results_stats.csv --check-thresholds --ci-mode

# Save to history and compare with previous run
python ../parse_load_results.py results_stats.csv --save-history --compare-last

# JSON output for scripting
python ../parse_load_results.py results_stats.csv --json
```

### Threshold Configuration

Edit `../thresholds.py` to adjust pass/fail criteria:
- `MAX_FAILURE_RATE`: Overall failure rate threshold (default: 1%)
- `RESPONSE_TIME_THRESHOLDS`: Per-endpoint P95/P50 limits
- `CI_SMOKE_THRESHOLDS`: Stricter thresholds for CI smoke tests

### Historical Tracking

Results are automatically saved to `../results/load_test_history.json` when using `--save-history`.
The history file keeps the last 100 runs for trend analysis.

## CI/CD Integration

### GitHub Actions Workflow

A load test workflow is available at `.github/workflows/load-test.yml`:

```bash
# Trigger via GitHub UI:
# Actions → Load Test Smoke → Run workflow

# Or via gh CLI:
gh workflow run load-test.yml \
  -f users=10 \
  -f spawn_rate=2 \
  -f duration=2m \
  -f environment=preview
```

### Required Secrets

Add these secrets to your GitHub repository (Settings → Secrets → Actions):

| Secret | Description | Example |
|--------|-------------|---------|
| `LOADTEST_BYPASS_TOKEN` | Rate limit bypass token | `<LOAD_TEST_TOKEN>` |
| `LOADTEST_USERS` | Comma-separated test user emails | `sarah.chen@example.com,emma.johnson@example.com` |
| `LOADTEST_PASSWORD` | Password for test users | `Test1234` |

**Note**: Store real tokens in GitHub Secrets/env vars only; never commit them.
If secrets are not set, the workflow uses default values from CLAUDE.md.

### CI Smoke Test Configuration

| Setting | CI Smoke | Full Capacity |
|---------|----------|---------------|
| Users | 10 | 50-400 |
| Spawn Rate | 2/sec | 5-25/sec |
| Duration | 2m | 5m |
| Failure Threshold | 0% | 1% |

## Troubleshooting

### "Connection refused" errors
- Check if preview backend is running
- Verify `LOADTEST_BASE_URL` is correct

### No `e2e_full_latency` metric
- Verify both users share the same conversation
- Check `config/conversations.json` is correct
- Ensure SSE is receiving `new_message` events

### High error rates immediately
- Run S0 first to establish baseline
- Check backend logs for exceptions
- Verify test user credentials

### Tests hang at startup
- Check network connectivity to preview
- Verify Redis is healthy
- Look for authentication failures in logs
