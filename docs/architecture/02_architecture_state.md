# InstaInstru Architecture State
*Last Updated: January 2026 (Session v129)*

## 🗏 Service Layer Architecture (100% COMPLETE)

Service layer fully implemented with complete separation of concerns. All routes use services for business logic, all services use repositories for data access.

### Service Excellence Metrics
- **16+ services** at 8.5/10 average quality
- **All singletons eliminated** - 100% dependency injection
- **98 performance metrics** added
- **All methods under 50 lines**
- **Test coverage**: 95.45% (CI locked)

### Service Directory Structure
```
backend/app/services/
├── base.py                    # BaseService with transaction management
├── instructor_service.py      # Instructor profile CRUD
├── availability_service.py    # Week-based availability management
├── booking_service.py         # Full booking lifecycle
├── cache_service.py           # Redis/DragonflyDB integration
├── notification_service.py    # Email notifications via Resend
├── conflict_checker.py        # Booking conflict detection
├── slot_manager.py           # Time slot CRUD
├── week_operation_service.py  # Week copy and patterns
├── bulk_operation_service.py  # Bulk availability updates
├── auth_service.py           # Authentication operations
├── password_reset_service.py  # Password reset flow
└── [other services...]
```

### Key Service Features
1. **BaseService Class**: Transaction management, error handling, repository integration
2. **Dependency Injection**: All services via FastAPI dependencies
3. **Business Logic**: Routes only handle HTTP, services handle logic
4. **Performance Monitoring**: @measure_operation decorator, slow query detection

## 🤖 MCP Admin Copilot (v128-v129)

AI-powered admin interface for natural language operations through LLM clients.

### MCP Server Architecture
| Property | Value |
|----------|-------|
| **Total Tools** | 36 |
| **Modules** | 11 |
| **Auth** | OAuth2 M2M (WorkOS JWT) + static token fallback |
| **Framework** | FastMCP 2.14.3+ |
| **Transport** | Streamable HTTP with JSON responses |
| **Test Coverage** | 100% (163+ tests) |

### Tool Modules
| Module | Tools | Purpose |
|--------|-------|---------|
| **Celery Monitoring** | 7 | Worker status, queue depth, failed tasks, payment health |
| **Grafana Observability** | 8 | PromQL queries, dashboards, alerts, silences |
| **Sentry Tracking** | 4 | Top issues, issue details, event lookup, debug |
| **Admin Operations** | 6 | Bookings, payments pipeline, user lookup |
| **Service Catalog** | 2 | Services list, service lookup |
| **Instructor Mgmt** | 3 | List, coverage, detail |
| **Founding Funnel** | 2 | Funnel summary, stuck instructors |
| **Invite Management** | 4 | Preview, send, confirmation workflow |
| **Search Analytics** | 2 | Top queries, zero-result gaps |
| **Metrics Dictionary** | 1 | 50+ metric definitions with PromQL |

### Semantic Metrics Layer
Natural language metric queries via `instainstru_metrics_query`:
- "p99 latency" → `histogram_quantile(0.99, ...)`
- "error rate" → 5xx / total
- "slowest endpoints" → `topk(10, histogram_quantile(...))`

## 📊 Full-Stack Observability (v129)

### Sentry Integration
| Component | Integration | Key Features |
|-----------|-------------|--------------|
| **Backend** | `sentry-sdk[fastapi]` | Performance monitoring, transaction tracing |
| **Frontend** | `@sentry/nextjs` | Session replay, error boundaries |
| **MCP Server** | `MCPIntegration()` | Error tracking with git SHA releases |
| **Celery Beat** | Sentry Crons | Periodic task monitoring |

### Monitoring Tunnel
Frontend `/monitoring` route bypasses ad blockers for client-side error reporting.

## 🗄️ Repository Layer (100% COMPLETE)

Repository Pattern fully implemented across all services with pre-commit enforcement.

### Repository Status
- **17+ repositories** implemented
- **100% service coverage**
- **Zero direct DB queries** in services
- **Pre-commit hooks** prevent regression

### Core Repositories
- SlotManagerRepository (13 methods, 97% coverage)
- AvailabilityRepository (15+ methods)
- ConflictCheckerRepository (13 methods, 99% coverage)
- BookingRepository (Complete CRUD)
- UserRepository (User + timezone management)
- PermissionRepository (RBAC with 30 permissions)
- FavoritesRepository (Student favorites)
- ConversationStateRepository (Messaging archive/trash management)
- MessageRepository (Message persistence with delivered_at/read_by)
- RetrieverRepository (NL Search vector + text SQL)
- FilterRepository (PostGIS + availability filtering)
- RankingRepository (Instructor metrics)
- SearchAnalyticsRepository (Query tracking)

## 🎨 Frontend Architecture (SERVICE-FIRST COMPLETE)

### Current State
- **270+ services** operational
- **Service-first architecture** implemented
- **React Query mandatory** for all data fetching
- **Technical debt eliminated**

### Service Pattern
```typescript
export const availabilityService = {
  getWeek: (instructorId, date) => api.get(`/availability/week/${instructorId}/${date}`),
  saveWeek: (data) => api.post('/availability/week', data)
};
```

### Key Features
- Natural Language Search (10x accuracy improvement)
- Global useAuth hook for authentication
- Search history system with tracking
- Optimistic UI updates throughout

## 📊 Database Schema Architecture

### Core Database Tables

| Table | Purpose | Key Features |
|-------|---------|--------------|
| **users** | User accounts | ULID IDs, timezone, 2FA fields |
| **instructor_profiles** | Instructor details | Bio, photo, verified status |
| **services** | Service catalog | Soft delete, pricing, duration |
| **availability_slots** | Instructor availability | Bitmap-based (1440-bit/day) |
| **bookings** | Lesson bookings | Time-based (no slot FKs) |
| **messages** | Chat messages | delivered_at, read_by |
| **conversation_user_state** | Per-user inbox state | active/archived/trashed |
| **reviews** | Student reviews | 5-star, text, instructor responses |
| **user_favorites** | Student favorites | UNIQUE(user_id, instructor_id) |
| **platform_credits** | Student wallet | Balance tracking, top-ups |
| **referral_codes** | Referral program | Give $20/Get $20, fraud detection |
| **student_badges** | Achievements | 7 badge types, event-driven |
| **background_checks** | Checkr integration | Status, adverse action workflow |
| **user_addresses** | Address management | PostGIS geocoding |
| **instructor_service_areas** | Coverage areas | PostGIS regions |

### Key Architectural Decisions
1. **ULID IDs** - All IDs are 26-character strings (sortable, non-sequential)
2. **Bitmap Availability** - 1440-bit per day (70% storage reduction)
3. **Time-Based Booking** - No slot IDs, just {instructor_id, date, start_time, end_time}
4. **Per-User Conversation State** - Independent archive/trash per participant
5. **PostGIS Spatial** - Region boundaries, distance queries
6. **Event-Driven Badges** - Trigger-based achievement awarding
7. **Device Fingerprinting** - Referral fraud detection

## 📌 API Architecture

### API Versioning (Single Rule)
**ALL routes under `/api/v1/*`** - No exceptions (except /docs, /redoc, /openapi.json).

- **333 endpoints** total
- Infrastructure routes: `/api/v1/health`, `/api/v1/ready`, `/api/v1/metrics/*`
- Contract testing enforces OpenAPI compliance

### Route Organization (v121)
```
backend/app/routes/
├── v1/                         # ALL API routes
│   ├── addresses.py           # Address management
│   ├── admin/                 # Admin operations
│   ├── bookings.py            # Booking operations
│   ├── favorites.py           # Student favorites
│   ├── instructor_bookings.py # Instructor booking views
│   ├── instructors.py         # Instructor profiles
│   ├── messages.py            # Messaging system
│   ├── reviews.py             # Review system
│   ├── search.py              # NL instructor search
│   ├── services.py            # Service catalog
│   ├── health.py              # Health checks
│   ├── metrics.py             # Prometheus metrics
│   └── [other domains]        # All other v1 endpoints
└── (legacy routes deleted)     # Cleaned up in v121
```

### Request/Response Flow
```
Client Request
     ↓
Route Handler (thin controller)
     ↓
Service Layer (business logic)
     ↓
Repository Layer (data access)
     ↓
Database/Cache Layer
     ↓
Response Model (Pydantic)
     ↓
Client Response
```

## 🗺️ Location System (v127)

### Canonical Location Types
```
student_location    - Instructor travels to student
instructor_location - Student goes to instructor's studio
online              - Virtual lesson
neutral_location    - Meet at neutral location (park, library, etc.)
```

### Privacy Protection
- `jitter_coordinates()` adds 25-50m random offset using `secrets.SystemRandom()`
- Teaching locations expose only `approx_lat`, `approx_lng`, `neighborhood`
- Exact addresses never exposed in public APIs

### Instructor Capabilities
- `offers_travel` - Instructor travels to student locations
- `offers_at_location` - Instructor teaches at their studio
- `offers_online` - Instructor offers virtual lessons

### Service Area Validation
- PostGIS `ST_Covers` validates student location within instructor coverage
- Bulk coverage check endpoint with HTTP caching

## 🛏 Architectural Patterns

### Implemented Patterns
1. **Service Layer Pattern** - Business logic centralization
2. **Repository Pattern** - Data access abstraction (17+ repositories)
3. **Factory Pattern** - Repository creation
4. **Circuit Breaker** - Cache/OpenAI failure protection
5. **Cache-Aside** - Check cache, load on miss
6. **Layer Independence** - Availability and bookings separate
7. **Dependency Injection** - No global instances
8. **Service-First Frontend** - 270+ services
9. **Hybrid NL Search** - Regex fast-path + LLM for complex queries
10. **Request Budget** - Progressive degradation under load
11. **Advisory Locks** - Founding cap atomicity
12. **Defense-in-Depth Payments** - Redis mutex + PostgreSQL row locks (v123)
13. **Principal-Based Auth** - User and Service principals for MCP (v128)

## 🔐 Security & Privacy

### Security Implementation
- **Argon2id** password hashing (OWASP-recommended)
- **JWT authentication** with RBAC (30 permissions)
- **Pydantic validation** on all inputs
- **GCRA rate limiting** across endpoints
- **SSL/HTTPS** in production
- **Database safety** - 3-tier protection (INT/STG/PROD)
- **Timing-safe comparisons** for tokens (`secrets.compare_digest`)
- **OAuth2 M2M** for service-to-service auth (MCP)

### Privacy Framework
- **GDPR compliance** with data export
- **Right to be Forgotten** implementation
- **Automated retention** via Celery
- **IP hashing** for analytics
- **Schema-owned privacy** transformation

## 📈 Performance Architecture

### Current Optimizations
- **Database indexes** on common queries
- **Redis caching** with 80%+ hit rate
- **Eager loading** prevents N+1 queries
- **Connection pooling** optimized
- **Response times** <100ms average
- **Query monitoring** with slow query alerts

### Load Testing Results (v120)
- **150 concurrent users** - Stable with graceful degradation
- **5.9% failure rate** at limit (all retriable 503s)
- **Request budget** - Progressive degradation under load
- **Per-OpenAI semaphore** - Fast queries never blocked

### Infrastructure
- **Backend**: Render ($60/month total)
- **Frontend**: Vercel (Preview + Beta)
- **Database**: Supabase PostgreSQL
- **Cache**: Redis
- **Celery**: Background workers

## 🚨 Critical Architecture Issues

### Resolved ✅
- **Layer Independence** (Work Stream #9) - Complete
- **Single-Table Design** (Work Stream #10) - Backend complete
- **Public API** (Work Stream #12) - Complete
- **Repository Pattern** - 100% implementation
- **Frontend Technical Debt** - Service-first transformation complete

### All Systems Complete ✅
- Payment integration via Stripe Connect
- Reviews/ratings with instructor responses
- Background checks via Checkr
- Referral system with fraud detection
- Achievement/badge gamification
- 2FA with TOTP + backup codes
- Rate limiting with GCRA algorithm
- Dual environments (preview + beta)

## 🎯 Architecture Maturity

### Backend: A+ Grade
- Service Layer ✅
- Repository Pattern ✅ (17+ repositories)
- Database Schema ✅
- Caching Strategy ✅
- Authentication/RBAC ✅
- Error Handling ✅
- Test Infrastructure ✅ (2,516+ tests, 95.45% coverage)
- Performance Monitoring ✅
- Load Tested ✅ (150 users)
- Full-Stack Observability ✅ (Sentry)

### Frontend: A Grade
- TypeScript Strictest Config ✅ (0 errors)
- Service-First Architecture (270+ services) ✅
- React Query Integration ✅
- Natural Language Search ✅ (self-learning)
- API Contract Enforcement ✅
- Test Coverage ✅ (8,806+ tests, 95.08% coverage)

### MCP Server: A+ Grade
- OAuth2 M2M Authentication ✅
- Principal-Based Authorization ✅
- 36 Tools Across 11 Modules ✅
- 100% Test Coverage ✅ (163+ tests)
- Semantic Metrics Layer ✅

## 🏗️ Domain-Specific Architectures

### Payments (Stripe Connect) - Policy v2.1.1 (v123)
- **Pre-Authorization**: Authorize T-24hr, capture T+24hr
- **Platform Credits**: Auto-apply at checkout, balance tracking
- **Tiered Commissions**: 15% → 12% → 10% based on volume
- **Defense-in-Depth**: Redis mutex + PostgreSQL row locks
- **LOCK Mechanism**: 12-24h reschedule triggers anti-gaming protection
- **Credit Double-Spend**: SELECT FOR UPDATE + idempotency check
- **Checkout Race**: Fresh read after payment, cancel detection

### Rate Limiting (GCRA Algorithm)
- **Identity Chain**: User ID → IP fallback
- **Financial Protection**: Triple limits on booking/payment/refund
- **Runtime Config**: Hot-reload via HMAC-secured endpoints
- **Shadow Mode**: Observe before enforce

### Referral System
- **Student Referrals**: Give $20/Get $20 platform credits
- **Instructor Referrals**: $75 founding / $50 standard cash via Stripe Transfer (v124)
- **Fraud Detection**: Device fingerprinting, household limits, self-referral prevention
- **Attribution**: First-touch, email/phone verification

### Notifications (v125)
- **Multi-Channel**: Email (Resend), SMS (Twilio), Push (Web Push API), In-App (SSE)
- **User Preferences**: Per-category toggles (6 categories), per-channel control
- **Security Bypass**: Critical security notifications ignore preferences
- **Phone Verification**: 6-digit codes, rate limiting, brute-force protection

### Achievements (Gamification)
- **7 Badge Types**: Milestones, habits, excellence, verified
- **Event-Driven**: Trigger-based awarding on booking/review events
- **Hold Mechanism**: Quality badges require admin approval

### NL Search
- **Hybrid Parsing**: Regex fast-path + GPT-4o-mini for complex queries
- **5-Tier Location**: Exact → Alias → Substring → Fuzzy → Embedding → LLM
- **Self-Learning**: Click tracking creates location aliases automatically
- **6-Signal Ranking**: Relevance, quality, distance, price, freshness, completeness
- **Lesson Type Filter**: Online/in-person filter via `instructor_services.location_types` (v122)
- **"Near Me" Search**: User address lookup, reverse geocoding via PostGIS (v122)

### Founding Instructor System
- **Lifetime 8% Platform Fee**: vs 15% standard
- **Search Ranking Boost**: 1.5x multiplier
- **Tier Immunity**: Exempt from commission downgrades
- **Cap Enforcement**: PostgreSQL advisory locks for atomicity

### Inline Search Filters (v127)
- **Zocdoc-Style**: Pill buttons + dropdown filters in top bar
- **Draft State Pattern**: Changes apply on "Apply" click
- **Portal Rendering**: z-index stacking solved
- **Sorting**: Recommended, Price, Rating with null handling

## 📝 Architecture Decision Records

*See `architecture-decisions.md` for full rationale and implementation details*

Key decisions: ULID IDs, Bitmap Availability, 24hr Pre-Auth, Per-User State, GCRA Rate Limiting, API v1 Versioning, Dual Environments, Repository Pattern, Database Safety, Privacy Framework, NL Search Hybrid Parsing, Advisory Locks for Founding Cap, Location System Privacy (v127), Defense-in-Depth Payments (v123), OAuth2 M2M Auth (v128), Principal-Based Authorization (v128)
