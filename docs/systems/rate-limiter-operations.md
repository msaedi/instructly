# Rate Limiter Operations

*Last Updated: November 2025 (Session v117)*

## Overview

InstaInstru uses a **sliding window rate limiting** implementation backed by Redis. The system protects against DDoS attacks, brute force attempts, and resource exhaustion while maintaining a good user experience.

### Key Characteristics

| Aspect | Implementation |
|--------|---------------|
| Algorithm | Sliding window (sorted set-based) |
| Backend | Redis/DragonflyDB |
| Key Strategy | IP-based with user/email fallback |
| Default Limit | 100 requests/minute/IP |
| Auth Limit | 5 attempts/minute/IP |
| Metrics Limit | 6 requests/minute/IP |

### Rate Limit Tiers

| Tier | Limit | Window | Use Case |
|------|-------|--------|----------|
| General | 100/min | 60s | All API endpoints |
| Authentication | 5/min | 60s | Login, signup |
| Password Reset | 3/hour per email | 3600s | Password reset requests |
| BGC Invite | 10/hour | 3600s | Background check invitations |
| Metrics | 6/min | 60s | `/internal/metrics` endpoint |

---

## Architecture

### Middleware Stack

The rate limiter operates as ASGI middleware before reaching FastAPI routes:

```
Request → RateLimitMiddlewareASGI → FastAPI Routes
                    ↓
              Rate Limit Check
                    ↓
              Allowed? → Process Request
              Denied?  → 429 Response
```

### Implementation Files

| File | Purpose |
|------|---------|
| `app/middleware/rate_limiter.py` | Core limiter, decorators, admin functions |
| `app/middleware/rate_limiter_asgi.py` | ASGI middleware for global limiting |
| `app/core/config.py` | Rate limit configuration settings |

### Redis Data Structure

Rate limits use Redis sorted sets (ZSET) for sliding window tracking:

```
Key: rate_limit:{window_name}:{identifier}
Score: timestamp (float)
Member: timestamp string

Example:
rate_limit:general:192.168.1.1 = {
    "1701234567.123": 1701234567.123,
    "1701234568.456": 1701234568.456,
    ...
}
```

---

## Key Components

### 1. Core RateLimiter Class

Located in `backend/app/middleware/rate_limiter.py`:

```python
class RateLimiter:
    """Core rate limiting logic using sliding window algorithm."""

    def check_rate_limit(
        self, identifier: str, limit: int, window_seconds: int, window_name: Optional[str] = None
    ) -> Tuple[bool, int, int]:
        """
        Check if request is within rate limit.

        Args:
            identifier: Unique identifier (IP, user ID, email)
            limit: Maximum requests allowed
            window_seconds: Time window in seconds
            window_name: Optional name for the window (for cache key)

        Returns:
            Tuple of (allowed, requests_made, retry_after_seconds)
        """
        cache_key = self._get_cache_key(identifier, window_name)

        # Use Redis pipeline for atomic operations
        pipe = self.cache.redis.pipeline()
        now = time.time()
        window_start = now - window_seconds

        # 1. Remove entries outside the window
        pipe.zremrangebyscore(cache_key, 0, window_start)

        # 2. Count requests in current window
        pipe.zcard(cache_key)

        # 3. Add current request timestamp
        pipe.zadd(cache_key, {str(now): now})

        # 4. Set key expiration
        pipe.expire(cache_key, window_seconds + 60)

        results = pipe.execute()
        requests_in_window = results[1]

        if requests_in_window >= limit:
            # Calculate retry_after from oldest request
            oldest = self.cache.redis.zrange(cache_key, 0, 0, withscores=True)
            retry_after = int(oldest[0][1] + window_seconds - now)

            # Remove the request we just added (rejected)
            self.cache.redis.zrem(cache_key, str(now))

            return False, requests_in_window, retry_after

        return True, requests_in_window + 1, 0
```

### 2. ASGI Middleware

Located in `backend/app/middleware/rate_limiter_asgi.py`:

```python
class RateLimitMiddlewareASGI:
    """Pure ASGI middleware for rate limiting."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Skip non-HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Skip health checks and SSE endpoints
        path = scope.get("path", "")
        if path == "/health" or path.startswith(SSE_PATH_PREFIX):
            await self.app(scope, receive, send)
            return

        # Always allow CORS preflight
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # Get client IP (supports X-Forwarded-For, CF-Connecting-IP)
        client_ip = self._extract_client_ip(scope)

        # Check rate limit
        allowed, requests_made, retry_after = self.rate_limiter.check_rate_limit(
            identifier=client_ip,
            limit=self.general_limit,
            window_seconds=60,
            window_name="general"
        )

        if not allowed:
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    "code": "RATE_LIMIT_EXCEEDED",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.general_limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                },
            )
            await response(scope, receive, send)
            return

        # Process request with rate limit headers
        await self.app(scope, receive, send_wrapper)
```

### 3. Decorator-Based Rate Limiting

For endpoint-specific limits:

```python
from app.middleware.rate_limiter import rate_limit, RateLimitKeyType

@router.post("/login")
@rate_limit("5/minute", key_type=RateLimitKeyType.IP)
async def login(request: LoginRequest):
    """Login endpoint with IP-based rate limiting."""
    ...

@router.post("/password-reset")
@rate_limit("3/hour", key_type=RateLimitKeyType.EMAIL, key_field="email")
async def password_reset(request: PasswordResetRequest):
    """Password reset with email-based rate limiting."""
    ...
```

**Key Types:**

| Type | Identifier Source |
|------|-------------------|
| `IP` | Client IP address (supports X-Forwarded-For) |
| `USER` | Authenticated user ID from `current_user` |
| `EMAIL` | Email from request body or authenticated user |
| `ENDPOINT` | Request path |
| `COMPOSITE` | IP + path + user ID combined |

---

## Data Flow

### Request Flow

```
1. Request arrives at ASGI middleware

2. Extract client IP
   - Check CF-Connecting-IP header
   - Check X-Forwarded-For header
   - Fall back to direct client IP

3. Check exemptions
   - /health → Always allowed
   - /api/v1/sse/* → Always allowed (SSE)
   - OPTIONS → Always allowed (CORS)

4. Check rate limit
   - Query Redis sorted set
   - Count requests in window
   - Add current request

5. If limit exceeded:
   - Return 429 with Retry-After header
   - Log rate limit event

6. If allowed:
   - Add rate limit headers to response
   - Pass to application
```

### Response Headers

Every response includes rate limit headers:

```
X-RateLimit-Limit: 100       # Maximum requests allowed
X-RateLimit-Remaining: 73    # Requests remaining in window
X-RateLimit-Reset: 1701234627  # Unix timestamp when window resets
Retry-After: 45              # Seconds until retry (only on 429)
```

---

## Error Handling

### 429 Response Format

```json
{
  "detail": "Rate limit exceeded. Try again in 45 seconds.",
  "code": "RATE_LIMIT_EXCEEDED",
  "retry_after": 45
}
```

### Graceful Degradation

When Redis is unavailable:
- Rate limiting is bypassed
- Warning is logged
- Requests proceed normally

```python
if not self.cache.redis:
    logger.warning("Rate limiting bypassed - cache unavailable")
    return True, 0, 0  # Allow request
```

### Cache Errors

```python
try:
    # Rate limit check
except Exception as e:
    logger.error(f"Rate limit check failed: {e}")
    return True, 0, 0  # Fail open
```

---

## Monitoring

### Logging

Rate limit events are logged with structured data:

```python
logger.warning(
    "[RATE_LIMIT] 429",
    extra={
        "path": path,
        "method": method,
        "bucket": "general",
        "key": client_ip,
        "count_before": requests_made,
        "limit": self.general_limit,
        "retry_after": retry_after,
    },
)
```

### Admin Statistics

```python
class RateLimitAdmin:
    @staticmethod
    def get_rate_limit_stats() -> Dict[str, Any]:
        """Get statistics about current rate limits."""
        return {
            "total_keys": count_of_rate_limit_keys,
            "by_type": {"general": 150, "auth": 10, ...},
            "top_limited": [
                {"key": "rate_limit:general:1.2.3.4", "requests": 95, "ttl_seconds": 45},
                ...
            ]
        }
```

### Prometheus Metrics

Rate limiting metrics can be exported via `/internal/metrics`:
- `rate_limit_requests_total` - Total rate-limited requests
- `rate_limit_429_total` - Total 429 responses by path

---

## Common Operations

### Check Current Limits for IP

```python
from app.middleware.rate_limiter import RateLimiter

limiter = RateLimiter()
remaining = limiter.get_remaining_requests(
    identifier="192.168.1.1",
    limit=100,
    window_seconds=60,
    window_name="general"
)
print(f"Remaining requests: {remaining}")
```

### Reset Limits for User

```python
from app.middleware.rate_limiter import RateLimiter

limiter = RateLimiter()
success = limiter.reset_limit(
    identifier="user_01K2...",
    window_name="login_5per60s"
)
```

### Reset All Limits for Email Pattern

```python
from app.middleware.rate_limiter import RateLimitAdmin

count = RateLimitAdmin.reset_all_limits("email_*@example.com")
print(f"Reset {count} rate limits")
```

### Query Redis Directly

```bash
# List all rate limit keys
redis-cli KEYS "rate_limit:*"

# Check specific IP's request count
redis-cli ZCARD "rate_limit:general:192.168.1.1"

# View request timestamps
redis-cli ZRANGE "rate_limit:general:192.168.1.1" 0 -1 WITHSCORES

# Clear rate limit for IP
redis-cli DEL "rate_limit:general:192.168.1.1"
```

---

## Troubleshooting

### Users Getting 429 Unexpectedly

1. **Check if behind proxy** - Ensure X-Forwarded-For is properly configured

2. **Shared IP issue** - NAT/VPN users share IP:
   ```bash
   redis-cli ZCARD "rate_limit:general:$IP"
   ```

3. **Check window size** - May be hitting limit near window boundary

4. **Verify limit settings**:
   ```python
   print(settings.rate_limit_general_per_minute)
   ```

### Rate Limiting Not Working

1. **Check if enabled**:
   ```python
   print(settings.rate_limit_enabled)  # Should be True
   ```

2. **Verify Redis connection**:
   ```python
   from app.services.cache_service import get_cache_service
   cache = get_cache_service()
   print(cache.redis.ping())  # Should return True
   ```

3. **Check test mode**:
   ```python
   print(settings.is_testing)  # Should be False in production
   ```

### High False Positive Rate

1. **Review IP extraction logic** - May be getting proxy IP instead of client IP

2. **Check X-Forwarded-For trust** - May be accepting spoofed headers

3. **Consider user-based limiting** for authenticated endpoints

---

## Configuration

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `RATE_LIMIT_ENABLED` | `true` | Enable/disable rate limiting globally |
| `RATE_LIMIT_GENERAL_PER_MINUTE` | `100` | Default per-IP limit |
| `RATE_LIMIT_AUTH_PER_MINUTE` | `5` | Auth endpoint limit |
| `METRICS_RATE_LIMIT_PER_MIN` | `6` | /internal/metrics limit |

### Adding New Rate Limits

1. **Add configuration**:
   ```python
   # In app/core/config.py
   rate_limit_new_feature_per_hour: int = Field(
       default=10, description="New feature rate limit per hour per IP"
   )
   ```

2. **Apply to endpoint**:
   ```python
   @router.post("/new-feature")
   @rate_limit("10/hour", key_type=RateLimitKeyType.USER)
   async def new_feature(...):
       ...
   ```

3. **Or in ASGI middleware for path patterns**:
   ```python
   if method == "POST" and path.startswith("/api/v1/new-feature"):
       allowed, _, retry_after = self.rate_limiter.check_rate_limit(
           identifier=f"new_feature:{client_ip}",
           limit=10,
           window_seconds=3600,
           window_name="new_feature",
       )
   ```

### Testing Rate Limits

```python
@pytest.fixture
def enable_rate_limiting():
    """Enable rate limiting for tests."""
    original_value = settings.rate_limit_enabled
    settings.rate_limit_enabled = True
    yield
    settings.rate_limit_enabled = original_value

@pytest.fixture
def clear_rate_limits():
    """Clear rate limit cache before tests."""
    cache = get_cache_service()
    for key in cache.redis.scan_iter(match="rate_limit:*"):
        cache.redis.delete(key)
    yield
```

---

## Local Development

In local/preview mode, some endpoints are exempt from rate limiting:
- `/auth/me`
- `/api/public/session/guest`
- GET `/api/v1/reviews/instructor/*`
- GET `/api/v1/services/*`
- GET `/api/v1/instructors*`

This prevents development friction while maintaining security in production.

---

## Related Documentation

- Middleware: `backend/app/middleware/rate_limiter.py`
- ASGI Middleware: `backend/app/middleware/rate_limiter_asgi.py`
- Configuration: `backend/app/core/config.py`
- Tests: `backend/tests/unit/middleware/test_rate_limiter.py`
