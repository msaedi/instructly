import time

from app.ratelimit.gcra import gcra_decide


def test_burst_allows_initial_requests():
    now = time.time()
    tat = None
    rate = 60
    burst = 5

    # First burst+1 requests should generally pass depending on definition
    allowed_count = 0
    for _ in range(burst + 1):
        tat, decision = gcra_decide(now, tat, rate, burst)
        if decision.allowed:
            allowed_count += 1
    assert allowed_count >= burst  # allow at least burst, often burst+1 depending on model


def test_rate_blocks_when_over_limit():
    now = time.time()
    tat = None
    rate = 60
    burst = 0

    # First allowed
    tat, decision = gcra_decide(now, tat, rate, burst)
    assert decision.allowed

    # Immediate next should be blocked (no burst)
    tat, decision = gcra_decide(now, tat, rate, burst)
    assert not decision.allowed
    assert decision.retry_after_s >= 0


def test_boundary_allows_after_interval():
    now = time.time()
    tat = None
    rate = 6  # 10s interval
    burst = 0

    tat, d1 = gcra_decide(now, tat, rate, burst)
    assert d1.allowed

    later = now + 10.05
    tat, d2 = gcra_decide(later, tat, rate, burst)
    assert d2.allowed
