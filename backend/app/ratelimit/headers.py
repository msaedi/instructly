from fastapi import Response


def set_rate_headers(res: Response, remaining: int, limit: int, reset_epoch_s: float, retry_after_s: float | None):
    res.headers["X-RateLimit-Remaining"] = str(max(remaining, 0))
    res.headers["X-RateLimit-Limit"] = str(limit)
    res.headers["X-RateLimit-Reset"] = str(int(reset_epoch_s))
    if retry_after_s and retry_after_s > 0:
        res.headers["Retry-After"] = str(int(retry_after_s))


def set_policy_headers(res: Response, bucket: str, shadow: bool):
    res.headers["X-RateLimit-Policy"] = bucket
    res.headers["X-RateLimit-Shadow"] = "true" if shadow else "false"
