import time
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class Decision:
    allowed: bool
    retry_after_s: float
    remaining: int
    limit: int
    reset_epoch_s: float


def _to_interval_s(rate_per_min: int) -> float:
    if rate_per_min <= 0:
        return float("inf")
    return 60.0 / float(rate_per_min)


def gcra_decide(
    now_s: float,
    last_tat_s: Optional[float],
    rate_per_min: int,
    burst: int,
) -> Tuple[float, Decision]:
    """
    Generalized Cell Rate Algorithm (token-bucket equivalent) pure decision function.

    Args:
        now_s: current wall time in seconds (epoch)
        last_tat_s: last Theoretical Arrival Time stored for the key (epoch seconds), or None if new
        rate_per_min: permitted average request rate per minute
        burst: additional burst capacity (in requests)

    Returns:
        (new_tat_s, Decision)
    """
    interval = _to_interval_s(rate_per_min)
    limit_capacity = max(1, int(rate_per_min if burst <= 0 else rate_per_min + burst))

    if interval == float("inf"):
        # Zero rate -> always blocked
        reset_epoch_s = (last_tat_s or now_s) + interval
        decision = Decision(False, retry_after_s=float("inf"), remaining=0, limit=0, reset_epoch_s=reset_epoch_s)
        return last_tat_s or now_s, decision

    # TAT baseline is last_tat_s, or a time in the past which allows immediate request
    tat = last_tat_s if last_tat_s is not None else now_s - (burst * interval)

    # Arrival at time now is permitted if now_s >= tat - burst*interval
    allowed = now_s >= tat - (burst * interval)
    if allowed:
        # Update TAT = max(tat, now) + interval
        new_tat = max(tat, now_s) + interval
        # Remaining tokens approx = floor((tat' - now) / interval) within [0, limit_capacity]
        remaining_float = max(0.0, (new_tat - now_s) / interval)
        remaining = max(0, int(burst - (remaining_float - 1)))  # approximate tokens left
        # Reset occurs when bucket fully refills back to burst -> time when remaining reaches burst
        reset_epoch_s = now_s + max(0.0, (burst * interval))
        decision = Decision(True, retry_after_s=0.0, remaining=remaining, limit=burst + 1, reset_epoch_s=reset_epoch_s)
        return new_tat, decision
    else:
        # Compute retry after: time until allowed again
        allow_at = tat - (burst * interval)
        retry_after = max(0.0, allow_at - now_s)
        # Remaining is zero when blocked
        reset_epoch_s = now_s + max(0.0, (burst * interval))
        decision = Decision(False, retry_after_s=retry_after, remaining=0, limit=burst + 1, reset_epoch_s=reset_epoch_s)
        return tat, decision
