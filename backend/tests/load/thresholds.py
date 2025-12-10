"""
Load Test Pass/Fail Thresholds Configuration.

These thresholds define what constitutes a passing load test.
Values are in milliseconds unless otherwise specified.
"""

# Overall failure rate threshold (percent)
MAX_FAILURE_RATE = 1.0  # 1% max failure rate

# Response time thresholds (P95, milliseconds)
RESPONSE_TIME_THRESHOLDS = {
    # Authentication
    "login": {
        "p95_max": 20000,  # 20s - includes bcrypt hashing
        "p50_max": 10000,  # 10s
    },
    "auth_check": {
        "p95_max": 2000,  # 2s
        "p50_max": 1000,  # 1s
    },
    # Messaging
    "send_message": {
        "p95_max": 5000,  # 5s
        "p50_max": 2000,  # 2s
    },
    # SSE
    "sse_stream": {
        "p95_max": 5000,  # 5s (connection establishment)
        "p50_max": 1000,  # 1s
    },
    # Custom SSE metrics
    "ttfe": {  # Time To First Event
        "p95_max": 1000,  # 1s
        "p50_max": 500,  # 500ms
    },
    "e2e_full_latency": {  # End-to-end message delivery
        "p95_max": 2000,  # 2s
        "p50_max": 1000,  # 1s
    },
}

# CI Smoke test thresholds (stricter, smaller test)
CI_SMOKE_THRESHOLDS = {
    "max_failure_rate": 0.0,  # Zero tolerance for smoke tests
    "login": {"p95_max": 15000},
    "send_message": {"p95_max": 3000},
    "ttfe": {"p95_max": 800},
    "e2e_full_latency": {"p95_max": 1500},
}

# Capacity test warning thresholds
CAPACITY_WARNING_THRESHOLDS = {
    "cpu_percent": 70,
    "memory_mb": 1600,  # 1.6GB
}

CAPACITY_CRITICAL_THRESHOLDS = {
    "cpu_percent": 80,
    "memory_mb": 1800,  # 1.8GB
}
