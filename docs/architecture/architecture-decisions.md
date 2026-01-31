# InstaInstru Architecture Decisions
*Last Updated: January 2026 (Session v129)*

## Core Architecture Decisions

| Decision | Status | Implementation | Impact |
|----------|--------|---------------|---------|
| **One-Way Relationships** | ✅ Active | Bookings reference slots (nullable), slots don't reference bookings | Prevents circular dependencies, cleaner transactions |
| **Service Layer Pattern** | ✅ Active | All business logic in services, thin routes | 100% routes use services, clean separation |
| **Repository Pattern** | ✅ Active | All data access via repositories, no direct DB in services | 100% implementation, pre-commit enforcement |
| **Soft Delete Strategy** | ✅ Active | `is_active` flag for services with bookings | Preserves referential integrity |
| **Cache Strategy** | ✅ Active | Redis with cache-aside pattern, circuit breaker | 80%+ hit rate, <2ms reads |
| **No PostgreSQL Enums** | ✅ Active | VARCHAR with CHECK constraints | Avoids SQLAlchemy issues |
| **Stay Synchronous** | ✅ Active | No async migration, 124ms adequate | Simpler codebase, easier debugging |
| **Layer Independence** | ✅ Active | Availability operations never check bookings | True architectural separation |
| **Single-Table Availability** | ✅ Active | Just availability_slots table | No InstructorAvailability table, simpler queries |
| **ULID Architecture** | ✅ Active | All IDs are 26-char strings | Better sortability than UUIDs |
| **RBAC System** | ✅ Active | 30 permissions, not role-based | `require_permission()` not role checks |
| **Database Safety** | ✅ Active | 3-tier INT/STG/PROD | Default to INT, production requires confirmation |
| **Clean Break Philosophy** | ✅ Active | No backward compatibility during dev | Edit existing migrations, don't create new |
| **Time-Based Booking** | ✅ Active | No slot IDs, just time ranges | `{instructor_id, date, start_time, end_time}` |
| **No Singletons** | ✅ Active | Dependency injection everywhere | All services use DI pattern |
| **Schema-Owned Privacy** | ✅ Active | Schemas handle privacy transformation | `InstructorInfo.from_user()` returns "FirstName L." |
| **React Query Mandatory** | ✅ Active | All frontend data fetching uses React Query | No fetch() or useEffect for API calls |
| **Bitmap Availability** | ✅ Active | 1440-bit per day (minutes-based) | 70% storage reduction vs slots, atomic week saves |
| **24hr Pre-Authorization** | ✅ Active | Authorize T-24hr, capture T+24hr | Chargeback protection, student confirmation window |
| **GCRA Rate Limiting** | ✅ Active | Runtime config, shadow mode | Triple financial protection, consistent behavior |
| **API v1 Versioning** | ✅ Active | All routes under `/api/v1/*` | Contract testing, safe evolution, ready for v2 |
| **Dual Environments** | ✅ Active | Preview + Beta domains | Phased rollout, stakeholder testing |
| **Two-Factor Auth** | ✅ Active | TOTP + backup codes | Instructor account security |
| **Referral Fraud Detection** | ✅ Active | Device fingerprinting, household limits | Prevent abuse while enabling growth |
| **Event-Driven Badges** | ✅ Active | Trigger-based achievement awarding | Gamification without manual tracking |
| **Background Checks** | ✅ Active | Checkr integration, adverse action workflow | Trust & safety compliance |
| **NL Search Hybrid Parsing** | ✅ Active | Regex fast-path + LLM for complex queries | 70%+ queries handled by regex (v118) |
| **5-Tier Location Resolution** | ✅ Active | Exact → Alias → Fuzzy → Embed → LLM | Graceful degradation for locations (v118) |
| **Self-Learning Aliases** | ✅ Active | Click tracking creates location aliases | System improves automatically (v119) |
| **Request Budget** | ✅ Active | Progressive degradation under load | 150 user capacity verified (v120) |
| **Advisory Locks for Cap** | ✅ Active | PostgreSQL advisory locks for founding cap | TOCTOU race condition prevention (v121) |
| **Single API Version Rule** | ✅ Active | ALL routes under `/api/v1/*` | No confusion, single rule (v121) |
| **Shared Origin Validation** | ✅ Active | Single `is_allowed_origin()` utility | Security-critical single implementation (v121) |
| **Transaction Before Invalidation** | ✅ Active | Commit DB before clearing cache | Prevents race conditions (v122) |
| **First-Lesson Referral Trigger** | ✅ Active | Payout on first completed lesson | Faster reward experience (v124) |
| **Security Notifications Bypass** | ✅ Active | Critical alerts ignore preferences | Security > user preference (v125) |
| **Location System Canonical Types** | ✅ Active | 4 types with privacy jittering | Clear semantics, address privacy (v127) |
| **OAuth2 M2M Auth** | ✅ Active | WorkOS JWT for MCP-to-backend | Service-to-service security (v128) |
| **Principal-Based Authorization** | ✅ Active | User and Service principals | Unified audit logging (v128) |
| **Full-Stack Sentry** | ✅ Active | Sentry across all components | Unified observability (v129) |
| **Timing-Safe Comparisons** | ✅ Active | `secrets.compare_digest()` everywhere | Prevents timing attacks (v129) |

## Defensive Measures (Preventing Regression)

| Hook | Purpose | Enforcement |
|------|---------|-------------|
| **check-repository-pattern** | Blocks `db.query()` in services | Pre-commit + CI/CD |
| **check-timezone-usage** | Blocks `date.today()` in user code | Pre-commit + CI/CD |
| **api-contracts** | Ensures Pydantic response models | Pre-commit + CI/CD |

## Key Implementation Patterns

### Repository Pattern
```python
# ✅ CORRECT
self.repository.get_user_by_id(user_id)

# ❌ BLOCKED by pre-commit
self.db.query(User).filter(...)
```

### Service Pattern
```python
class BookingService(BaseService):
    def __init__(self, db, repository=None):
        self.repository = repository or BookingRepository(db)

    @measure_operation
    def create_booking(self, data):
        with self.transaction():
            # Business logic here
```

### Time-Based Booking
```python
# No slot IDs, just time ranges
booking = {
    "instructor_id": instructor_id,
    "booking_date": date,
    "start_time": "09:00",
    "end_time": "10:00",
    "service_id": service_id
}
```

### Privacy Pattern
```python
class InstructorInfo:
    @classmethod
    def from_user(cls, user):
        # Never expose full last name
        return cls(
            first_name=user.first_name,
            last_initial=user.last_name[0] if user.last_name else ""
        )
```

## Migration Strategy

- **Development Phase**: Modify existing migrations in `alembic/versions/`
- **No New Migrations**: Don't use `alembic revision` until production
- **Clean History**: Squash migrations to show ideal path
- **Test with INT**: `python scripts/prep_db.py int`

## Infrastructure Decisions

| Component | Choice | Reason |
|-----------|--------|--------|
| **Database** | PostgreSQL via Supabase | PostGIS + pgvector support |
| **Cache** | Single Redis instance | Handles cache + Celery + sessions |
| **Background Jobs** | Celery + Beat | Async processing, scheduled tasks |
| **Email** | Resend API | Simple, reliable |
| **Assets** | Cloudflare R2 | 80% bandwidth reduction |
| **Hosting** | Render + Vercel | $60/month total |
| **CI Database** | Custom image with PostGIS + pgvector | Required for spatial + NL search |

## Critical Rules

1. **ALL IDs are ULIDs** - 26-character strings, never integers
2. **No fetch() in frontend** - React Query only
3. **No db.query() in services** - Repositories only
4. **No date.today() in user code** - Use timezone-aware utilities
5. **No slot IDs** - Time-based booking only
6. **No new migrations during dev** - Modify existing files
7. **Default to INT database** - Production requires explicit confirmation

### Timezone Architecture (v123)
**Decision**: Store UTC timestamps with timezone context, use TimezoneService for all conversions.

**New Fields**:
- `booking_start_utc`: Canonical UTC timestamp
- `booking_end_utc`: Canonical UTC timestamp
- `lesson_timezone`: IANA timezone ID for the lesson
- `instructor_tz_at_booking`: Snapshot of instructor TZ
- `student_tz_at_booking`: Snapshot of student TZ

**Rules**:
- In-person lessons: Instructor's timezone
- Online lessons: Instructor's timezone
- All comparisons: Use UTC
- DST spring-forward gaps: Reject with user-friendly error
- DST fall-back overlaps: Use first occurrence
- Wall-clock preservation: "2 PM" stays "2 PM" across DST

**Enforcement**:
- Pre-commit hook: check_timezone_patterns.py
- Exception marker: `# tz-pattern-ok: <reason>`

**Rationale**: Fixes min-advance check bug where local times were incorrectly treated as UTC.

## Messaging Architecture Decisions (v117)

### Per-User Conversation State
**Decision**: Conversation state (active/archived/trashed) is per-user, not global.

**Rationale**:
- Each participant can independently organize their inbox
- Student archives conversation, instructor still sees it
- Better privacy and UX

**Implementation**:
```sql
conversation_user_state:
  - booking_id (FK)
  - user_id (FK)
  - state: 'active' | 'archived' | 'trashed'
  - UNIQUE(booking_id, user_id)
```

### Auto-Restore on New Message
**Decision**: Archived/trashed conversations automatically restore to active when new message arrives.

**Rationale**:
- Prevents orphaned conversations
- Users never miss important messages
- Better than manual check

**Implementation**:
```python
if conversation.state in ['archived', 'trashed']:
    restore_to_active()
    notify_user()
```

### Conversation-Level vs Message-Level State
**Decision**: State applies to entire conversation, not individual messages.

**Rationale**:
- Simpler mental model
- Matches user expectations ("archive this conversation")
- Avoids complex filtering logic

**Anti-Pattern**: Filtering messages by `isArchived` flag (removed in v117)

### Separate Unfiltered Queries for Notifications
**Decision**: Notification badge/dropdown uses separate unfiltered query.

**Rationale**:
- Badge should show ALL unread messages
- Current filter (Archived/Trash) shouldn't hide notifications
- User never misses important messages

## NL Search Architecture Decisions (v118-v119)

### Hybrid Parsing
**Decision**: Use regex fast-path for simple queries, LLM only for complex ones.

**Rationale**:
- 70%+ queries handled by regex (sub-10ms)
- LLM only for complex multi-constraint queries
- Cost and latency optimization

### 5-Tier Location Resolution
**Decision**: Graceful degradation through 5 location resolution tiers.

**Tiers**:
1. Exact match (instant)
2. Alias lookup ("ues" → "Upper East Side")
3. Fuzzy match (typo tolerance)
4. Embedding similarity (semantic)
5. LLM resolution (last resort)

**Rationale**: Each tier faster/cheaper than next, fallback ensures resolution.

### Self-Learning Aliases
**Decision**: Click tracking creates location aliases automatically.

**Flow**:
1. User searches unresolved location
2. Click tracked with resulting region
3. After 5+ similar clicks (70%+ same region)
4. Daily Celery task creates alias
5. Future searches resolve instantly

**Rationale**: System improves without manual intervention.

### 6-Signal Ranking
**Decision**: Multi-signal ranking formula for search results.

**Formula**:
```
score = 0.35×relevance + 0.25×quality + 0.15×distance +
        0.10×price + 0.10×freshness + 0.05×completeness +
        audience_boost + skill_boost
```

**Rationale**: Balances multiple factors for best-fit instructors.

## Production Hardening Decisions (v120)

### Request Budget
**Decision**: Progressive degradation under load via request budgets.

**Degradation Levels**:
| Budget Remaining | Skip | Result |
|------------------|------|--------|
| >300ms | Nothing | Full semantic search |
| 150-300ms | Tier 5 LLM | Tier 4 + text |
| 80-150ms | Vector search | Text-only |
| <80ms | Full Burst 2 | Minimal results |

**Rationale**: Better partial results than timeouts/crashes.

### Per-OpenAI Semaphore
**Decision**: Separate semaphore for OpenAI calls, not full pipeline.

**Before**: Fast queries blocked by slow Tier 4/5 queries.
**After**: Only OpenAI calls gated, fast queries never blocked.

**Config**:
```
UNCACHED_SEARCH_CONCURRENCY=6      # Soft limit per worker
OPENAI_CALL_CONCURRENCY=3          # Hard limit on OpenAI calls
```

## Founding Instructor System Decisions (v121)

### Advisory Locks for Cap
**Decision**: PostgreSQL advisory lock instead of row-level locks.

**Rationale**:
- Row-level `FOR UPDATE` on all profiles causes table-wide contention
- Advisory lock serializes founding claims without blocking other queries
- Lock key: `0x494E5354_464F554E` ("INSTFOUN" in hex)

### Shared Founding Logic
**Decision**: Extract founding status granting to `BetaService.try_grant_founding_status()`.

**Rationale**:
- Logic was duplicated between `auth.py` and `v1/auth.py`
- Single source of truth for cap enforcement
- Returns `(granted: bool, message: str)` for observability

### Single API Version Rule
**Decision**: ALL routes under `/api/v1/*`, no exceptions.

**Rationale**:
- Pre-launch, no production traffic to break
- Eliminates "is this migrated?" confusion
- Infrastructure routes (health, ready, metrics) also moved
- Only exceptions: `/docs`, `/redoc`, `/openapi.json`

### Shared Origin Validation
**Decision**: Create shared `app/utils/url_validation.py`.

**Rationale**:
- `is_allowed_origin()` was duplicated in payments.py and stripe_service.py
- Security-critical code should have single implementation
- Restricts to explicit allowed IPs only

## Stripe Network Call Decisions (v123)

### Stripe Calls Outside Transactions
**Decision**: All Stripe API calls must be made OUTSIDE database transactions.

**Rationale**:
- Stripe calls take 100-500ms (network latency)
- DB transactions hold row locks
- Holding locks for 500ms causes contention and slow queries
- Load testing revealed this as primary bottleneck at 150+ users

**Pattern**:
```python
# ❌ BAD: Stripe inside transaction (holds lock 400ms)
with self.transaction():
    booking = self.repo.get(id)
    stripe.PaymentIntent.capture(booking.pi_id)  # 400ms network
    booking.status = "captured"

# ✅ GOOD: Stripe outside transaction (two 5ms locks)
# Phase 1: Read
with self.transaction():
    booking = self.repo.get(id)
    pi_id = booking.payment_intent_id

# Phase 2: Network (no lock)
result = stripe.PaymentIntent.capture(pi_id)

# Phase 3: Write
with self.transaction():
    booking.status = "captured"
```

**Error Handling**:
- If Phase 2 fails: Log error, update status to failed state in Phase 3
- If Phase 3 fails: Stripe already succeeded - use idempotency keys to safely retry, or reconcile via webhook
- Webhooks provide eventual consistency guarantee

**Identified Bottlenecks Fixed**:
| Method | Before (lock held) | After (lock held) |
|--------|-------------------|-------------------|
| `cancel_booking` | 350-800ms | 10-20ms |
| `process_booking_payment` | 400-800ms | 10-20ms |
| `save_payment_method` | 250-500ms | 10-20ms |
| `create_payment_intent` | 200-400ms | 10-20ms |
| `confirm_payment_intent` | 200-400ms | 10-20ms |

**Added**: December 2025 (v123)

## Cache Invalidation Decisions (v122)

### Transaction Before Invalidation
**Decision**: Always commit transaction before cache invalidation.

**Pattern**:
```python
with self.transaction():
    # Database operations
    pass
# After block exits (commit done)
invalidate_cache(keys)
```

**Rationale**: Prevents race condition where cache is cleared but DB not yet visible.

### No Browser Caching for Availability
**Decision**: Use `Cache-Control: private, no-cache, must-revalidate` for availability.

**Rationale**:
- `max-age=300` was causing 5-minute stale windows
- Server-side Redis cache still provides performance
- ETag enables efficient 304 responses

## Instructor Referral Decisions (v124)

### Platform-Funded Transfers
**Decision**: Referral bonuses are Stripe Transfers from platform balance, not tied to specific booking payments.

**Rationale**: Unlike instructor payouts from lessons (which come from captured PaymentIntents), referral bonuses are platform marketing spend.

### First-Lesson Trigger
**Decision**: Payout triggers on first completed lesson, not after 3 lessons.

**Rationale**: Faster reward = better referrer experience. First lesson proves instructor viability.

### Cash Payout (Not Platform Credits)
**Decision**: Instructors receive cash via Stripe Transfer, not platform credits.

**Rationale**: Cash is more valuable/motivating for instructors. Different from student referrals which give platform credits.

## Notification System Decisions (v125)

### Multi-Channel Delivery
**Decision**: Support Email (Resend), SMS (Twilio), Push (Web Push API), In-App (SSE).

**Rationale**: Different users prefer different channels. Critical notifications use multiple channels.

### Security Notifications Bypass Preferences
**Decision**: Always-on security notifications (new device login, password changed, 2FA changes, payment failed) ignore user preferences.

**Rationale**: Security > user preference. Users must know about account security events.

### Phone Verification Protection
**Decision**: 5-attempt limit with code invalidation, timing-safe comparison.

**Rationale**: Prevents brute-force attacks. `secrets.compare_digest()` prevents timing attacks.

## Location System Decisions (v127)

### Four Canonical Location Types
**Decision**: Normalize to `student_location`, `instructor_location`, `online`, `neutral_location`.

**Previous State**: Mixed values like `in_person`, `remote`, `student_home`.

**Rationale**: Clear semantics, consistent API responses, no ambiguity.

### Privacy-Safe Coordinate Jittering
**Decision**: Add 25-50m random offset to teaching location coordinates using `secrets.SystemRandom()`.

**Implementation**:
```python
def jitter_coordinates(lat, lng):
    # Cryptographically secure random offset
    offset = secrets.SystemRandom().uniform(0.00025, 0.0005)
    return approx_lat, approx_lng
```

**Rationale**: Protects instructor home addresses while still enabling "Where They Teach" maps.

### Instructor Capability Flags
**Decision**: Three boolean flags on `instructor_services`: `offers_travel`, `offers_at_location`, `offers_online`.

**Rationale**: Simpler than location_types array. Clear UI mapping to 3-toggle interface.

## MCP Server Decisions (v128-v129)

### OAuth2 M2M Authentication
**Decision**: Use WorkOS M2M JWT tokens for service-to-service auth between MCP server and backend.

**Flow**:
1. MCP server fetches JWT from WorkOS (client_credentials grant)
2. JWT sent as Bearer token to backend
3. Backend verifies via JWKS with 1-hour cache

**Rationale**: Short-lived JWTs, automatic rotation, scope enforcement. Same provider as user auth.

### Principal-Based Authorization
**Decision**: Backend uses Principal abstraction to handle both human (UserPrincipal) and service (ServicePrincipal) actors.

```python
@runtime_checkable
class Principal(Protocol):
    @property
    def id(self) -> str: ...  # For audit trails
    @property
    def identifier(self) -> str: ...  # Email or client_id
    @property
    def principal_type(self) -> Literal["user", "service"]: ...
```

**Rationale**: Decouples auth from User model, enables service actors, unified audit logging.

### Semantic Metrics Layer
**Decision**: Map natural language metric queries to PromQL.

**Example**:
```python
"p99 latency" → histogram_quantile(0.99, ...)
"error rate" → 5xx / total
```

**Rationale**: AI agents can query metrics without knowing PromQL.

### Unauthenticated Discovery Methods
**Decision**: Allow `initialize`, `notifications/initialized`, `tools/list` without authentication.

**Rationale**: ChatGPT's "mixed-auth" pattern requires tool discovery before authentication.

## Sentry Integration Decisions (v129)

### Full-Stack Observability
**Decision**: Integrate Sentry across all components: Backend, Frontend, MCP Server, Celery Beat.

**Rationale**: Unified error tracking, performance monitoring, session replay across entire stack.

### Frontend Monitoring Tunnel
**Decision**: Add `/monitoring` route to tunnel client-side Sentry reports.

**Rationale**: Bypasses ad blockers that block direct Sentry connections.

### Celery Beat with Sentry Crons
**Decision**: Use Sentry Crons for periodic task monitoring.

**Rationale**: Visibility into scheduled task health (missed runs, failures, duration).

## Security Hardening Decisions (v129)

### Timing-Safe Token Comparison
**Decision**: Use `secrets.compare_digest()` for all token comparisons.

**Rationale**: Prevents timing attacks on service tokens and verification codes.

### Self-Referral Prevention
**Decision**: Proactive check in `attribute_signup()` to block users using their own referral code.

**Rationale**: Previous approach only caught this post-hoc via device fingerprinting.

### Rate Limiting on Public Invite Endpoint
**Decision**: Add `@rate_limit("5/hour", key_type=IP)` to `POST /api/v1/public/referrals/send`.

**Rationale**: Unauthenticated endpoint was potential email bombing/spam vector.
