# InstaInstru External Service Integrations
*Last Updated: January 2026 (Session v129+)*

## Overview

InstaInstru integrates with multiple external services to provide a complete marketplace experience. This document maps all external services, their purposes, integration flows, and required configuration.

| Service | Purpose | Critical? | Fallback Behavior |
|---------|---------|-----------|-------------------|
| [Stripe](#stripe) | Payments, Connect, Identity | **Yes** | Mock mode in development |
| [Checkr](#checkr) | Background checks | **Yes** | FakeCheckr client in non-prod |
| [Resend](#resend) | Transactional email | **Yes** | Console logging in dev |
| [Twilio](#twilio) | SMS notifications | **Yes** | Disabled gracefully |
| [Web Push](#web-push-notifications) | Browser push notifications | No | Disabled if VAPID not configured |
| [WorkOS](#workos) | M2M authentication | No | Feature disabled (MCP admin requires it) |
| [Sentry](#sentry) | Error tracking (full-stack) | No | Disabled gracefully |
| [Cloudflare R2](#cloudflare-r2) | Asset storage | **Yes** | NullStorageClient fallback |
| [Google Maps](#google-maps) | Geocoding, Places | **Yes** | Mapbox fallback |
| [Mapbox](#mapbox) | Geocoding fallback | No | Feature disabled |
| [OpenAI](#openai) | NL search parsing | No | Regex parser (degraded quality for complex queries) |
| [Redis](#redis) | Cache, Celery broker | **Yes** | App fails to start |
| [Celery](#celery) | Background task queue | **Yes** | App fails to start |
| [Supabase](#supabase-postgresql) | PostgreSQL database | **Yes** | App fails to start |
| [Render](#render) | Backend hosting | **Yes** | App won't deploy |
| [Vercel](#vercel) | Frontend hosting | **Yes** | App won't deploy |
| [Cloudflare Turnstile](#cloudflare-turnstile) | CAPTCHA | No | CAPTCHA disabled |
| [Prometheus/Grafana](#prometheus--grafana-cloud) | Metrics & dashboards | No | Disabled gracefully |

---

## Stripe

### Purpose
- **Payment processing** via PaymentIntents with 24hr pre-authorization
- **Stripe Connect** for instructor payouts (Express accounts)
- **Stripe Identity** for instructor verification
- **Platform credits** and transfers
- **Tiered commission fees** for platform revenue

### Integration Flow

```
Student Checkout Flow:
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    ┌──────────────┐
│ Create      │ →  │ Authorize    │ →  │ Capture T+24hr  │ →  │ Transfer to  │
│ PaymentIntent│    │ (manual)     │    │ (Celery task)   │    │ Instructor   │
└─────────────┘    └──────────────┘    └─────────────────┘    └──────────────┘

Instructor Onboarding:
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    ┌──────────────┐
│ Create      │ →  │ Stripe       │ →  │ account.updated │ →  │ Payouts      │
│ Express Acct│    │ Onboarding UI│    │ webhook         │    │ Enabled      │
└─────────────┘    └──────────────┘    └─────────────────┘    └──────────────┘
```

### Webhooks Received

| Event | Endpoint | Purpose |
|-------|----------|---------|
| `payment_intent.succeeded` | `/api/v1/payments/webhooks/stripe` | Confirm payment |
| `payment_intent.payment_failed` | `/api/v1/payments/webhooks/stripe` | Handle failures |
| `account.updated` | `/api/v1/payments/webhooks/stripe` | Instructor onboarding status |
| `payout.paid` | `/api/v1/payments/webhooks/stripe` | Instructor payout confirmation |
| `charge.refunded` | `/api/v1/payments/webhooks/stripe` | Refund processing |

### Environment Variables

```bash
# Required
STRIPE_SECRET_KEY=sk_live_...           # API key for backend
STRIPE_PUBLISHABLE_KEY=pk_live_...      # API key for frontend

# Webhook secrets (multiple for different endpoints)
STRIPE_WEBHOOK_SECRET=whsec_...         # Local dev (Stripe CLI)
STRIPE_WEBHOOK_SECRET_PLATFORM=whsec_...  # Platform events (deployed)
STRIPE_WEBHOOK_SECRET_CONNECT=whsec_...   # Connect events (deployed)

# Optional configuration
STRIPE_PLATFORM_FEE_PERCENTAGE=15       # Instructor commission rate (platform takes 15%, instructor gets 85%)
STRIPE_CURRENCY=usd                     # Default currency
```

### Key Files
- [backend/app/services/stripe_service.py](backend/app/services/stripe_service.py) - Main service (1,500+ LOC)
- [backend/app/routes/v1/payments.py](backend/app/routes/v1/payments.py) - API endpoints + webhook handler
- [backend/app/models/payment.py](backend/app/models/payment.py) - Payment models

---

## Checkr

### Purpose
Background checks for instructor verification via hosted invitations workflow.

### Integration Flow

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    ┌──────────────┐
│ Create      │ →  │ Create       │ →  │ Instructor      │ →  │ Webhooks for │
│ Candidate   │    │ Invitation   │    │ completes check │    │ status updates│
└─────────────┘    └──────────────┘    └─────────────────┘    └──────────────┘

Adverse Action (if consider result):
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    ┌──────────────┐
│ Pre-Adverse │ →  │ 7-day wait   │ →  │ Final Adverse   │ →  │ Instructor   │
│ Notice      │    │ period       │    │ Action          │    │ Restricted   │
└─────────────┘    └──────────────┘    └─────────────────┘    └──────────────┘
```

### Webhooks Received

| Event | Endpoint | Purpose |
|-------|----------|---------|
| `invitation.created` | `/api/v1/webhooks/checkr` | Track invitation status |
| `invitation.completed` | `/api/v1/webhooks/checkr` | Applicant submitted |
| `report.created` | `/api/v1/webhooks/checkr` | Report started |
| `report.updated` | `/api/v1/webhooks/checkr` | ETA updates |
| `report.completed` | `/api/v1/webhooks/checkr` | Final result (clear/consider) |
| `report.suspended` | `/api/v1/webhooks/checkr` | Report suspended |
| `report.canceled` | `/api/v1/webhooks/checkr` | Report canceled |

### Environment Variables

```bash
# Required
CHECKR_API_KEY=...                      # API key (sensitive)
CHECKR_WEBHOOK_USER=...                 # Basic auth username for webhooks
CHECKR_WEBHOOK_PASS=...                 # Basic auth password for webhooks

# Configuration
CHECKR_ENV=sandbox|production           # Target environment
CHECKR_FAKE=true|false                  # Use FakeCheckr (auto-true in non-prod)
CHECKR_DEFAULT_PACKAGE=basic_plus       # Default check package
CHECKR_API_BASE=https://api.checkr.com/v1  # API base URL (auto-set per env)

# Optional
CHECKR_HOSTED_WORKFLOW=...              # Custom workflow parameter
BGC_ENCRYPTION_KEY=...                  # Required in production for PII
BGC_SUPPRESS_ADVERSE_EMAILS=true        # Suppress emails in non-prod
```

### Key Files
- [backend/app/integrations/checkr_client.py](backend/app/integrations/checkr_client.py) - API client
- [backend/app/services/background_check_service.py](backend/app/services/background_check_service.py) - Invitation logic
- [backend/app/services/background_check_workflow_service.py](backend/app/services/background_check_workflow_service.py) - Webhook processing
- [backend/app/routes/v1/webhooks_checkr.py](backend/app/routes/v1/webhooks_checkr.py) - Webhook endpoint

---

## Resend

### Purpose
Transactional email for all user communications.

### Integration Flow

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ EmailService│ →  │ Jinja2       │ →  │ Resend API      │
│ .send_email │    │ Templates    │    │ .Emails.send()  │
└─────────────┘    └──────────────┘    └─────────────────┘
```

### Email Templates (23 total)

| Category | Templates |
|----------|-----------|
| **Authentication** (3) | `password_reset`, `welcome`, `password_reset_confirmation` |
| **Booking** (9) | `confirmation_student`, `confirmation_instructor`, `reminder_student`, `reminder_instructor`, `cancellation_student`, `cancellation_instructor`, `cancellation_confirmation_student`, `cancellation_confirmation_instructor`, `new_message` |
| **Security** (3) | `new_device_login`, `password_changed`, `2fa_changed` |
| **Background Check** (3) | `review_status`, `expiry_recheck`, `final_adverse` |
| **Reviews** (2) | `new_review`, `review_response` |
| **Referrals** (2) | `invite`, `invite_standalone` |
| **Payment** (1) | `payment_failed` |
| **Payout** (1) | `payout_sent` |
| **Beta** (1) | `invite` |

### Environment Variables

```bash
# Required
RESEND_API_KEY=re_...                   # Resend API key

# Configuration
EMAIL_PROVIDER=resend|console           # Provider selection (console for dev)
FROM_EMAIL="iNSTAiNSTRU <hello@instainstru.com>"  # Default sender
EMAIL_FROM_ADDRESS=hello@instainstru.com  # Override address
EMAIL_FROM_NAME=iNSTAiNSTRU              # Override name
EMAIL_REPLY_TO=support@instainstru.com   # Reply-to address
EMAIL_SENDER_PROFILES_FILE=config/email_senders.json  # Named sender profiles
```

### Key Files
- [backend/app/services/email.py](backend/app/services/email.py) - Email service
- [backend/app/services/template_service.py](backend/app/services/template_service.py) - Jinja2 templates
- [backend/app/services/template_registry.py](backend/app/services/template_registry.py) - Template registry
- [backend/config/email_senders.json](backend/config/email_senders.json) - Sender profiles

---

## Twilio

### Purpose
SMS notifications for booking reminders and verifications.

### Integration Flow

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ SMSService  │ →  │ Rate Limit   │ →  │ Twilio API      │
│ .send_sms() │    │ Check (Redis)│    │ messages.create │
└─────────────┘    └──────────────┘    └─────────────────┘
```

### Features
- Daily per-user rate limiting (default: 10/day)
- Message segment counting (GSM vs Unicode)
- Messaging Service SID support
- Phone verification required before sending

### Environment Variables

```bash
# Required (if SMS enabled)
TWILIO_ACCOUNT_SID=AC...                # Account SID
TWILIO_AUTH_TOKEN=...                   # Auth token (sensitive)
TWILIO_PHONE_NUMBER=+1...               # Sending number (E.164)

# Optional
TWILIO_MESSAGING_SERVICE_SID=MG...      # Messaging Service SID
SMS_ENABLED=true|false                  # Enable/disable SMS (default: false)
SMS_DAILY_LIMIT_PER_USER=10             # Daily limit per user
```

### Key Files
- [backend/app/services/sms_service.py](backend/app/services/sms_service.py) - SMS service
- [backend/app/services/sms_templates.py](backend/app/services/sms_templates.py) - Message templates

---

## Web Push Notifications

### Purpose
Browser push notifications for real-time user alerts using the Web Push Protocol with VAPID authentication.

### Integration Flow

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    ┌──────────────┐
│ Subscribe   │ →  │ Store        │ →  │ pywebpush       │ →  │ Browser      │
│ (frontend)  │    │ subscription │    │ .webpush()      │    │ notification │
└─────────────┘    └──────────────┘    └─────────────────┘    └──────────────┘
```

### Features
- **VAPID authentication**: Public/private key pair for server identification
- **Multi-device support**: Users can subscribe on multiple browsers
- **Auto-cleanup**: Expired subscriptions (404/410) automatically removed
- **Notification payloads**: Title, body, icon, badge, URL, custom data
- **Tag-based grouping**: Notifications can replace previous ones

### Environment Variables

```bash
# Required (for push notifications)
VAPID_PUBLIC_KEY=...                    # Public key for client subscription
VAPID_PRIVATE_KEY=...                   # Private key for signing (sensitive)
VAPID_CLAIMS_EMAIL=mailto:support@instainstru.com  # Contact email for VAPID
```

### Key Files
- [backend/app/services/push_notification_service.py](backend/app/services/push_notification_service.py) - Push service
- [backend/app/models/notification.py](backend/app/models/notification.py) - PushSubscription model
- [backend/app/routes/v1/push.py](backend/app/routes/v1/push.py) - Subscribe/unsubscribe endpoints
- [backend/app/schemas/push.py](backend/app/schemas/push.py) - Push schemas

---

## WorkOS

### Purpose
Machine-to-machine (M2M) authentication for service-to-service communication using OAuth2 Client Credentials flow.

### Integration Flow

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ M2M Client  │ →  │ JWT Token    │ →  │ JWKS Validation │
│ Request     │    │ in Header    │    │ (cached 1hr)    │
└─────────────┘    └──────────────┘    └─────────────────┘
```

### Environment Variables

```bash
# Required for M2M auth
WORKOS_JWKS_URL=https://api.workos.com/.well-known/jwks.json
WORKOS_M2M_AUDIENCE=...                 # Expected audience claim
WORKOS_ISSUER=...                       # Expected issuer claim
```

### Key Files
- [backend/app/m2m_auth.py](backend/app/m2m_auth.py) - M2M token verification

---

## Sentry

### Purpose
Full-stack error tracking, performance monitoring, session replay, and Celery task monitoring across backend, frontend, and MCP server.

### Integration Flow

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Exception   │ →  │ Sentry SDK   │ →  │ Sentry Cloud    │
│ or Error    │    │ Capture      │    │ Dashboard       │
└─────────────┘    └──────────────┘    └─────────────────┘

Frontend Error Tunnel (ad-blocker bypass):
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Client Error│ →  │ /monitoring  │ →  │ Sentry Cloud    │
│ or Event    │    │ tunnel route │    │ API             │
└─────────────┘    └──────────────┘    └─────────────────┘
```

### Backend Integration
- **FastAPI integration** with transaction style: endpoint
- **Celery integration** with Beat task monitoring
- **Trace/profile sampling**: 10% each
- **Health check filtering**: `/health`, `/health/lite`, `/ready` excluded
- **Failed request codes**: 403, 500-599 tracked
- **Request/user context middleware**: User ID, email, request ID attached

### Frontend Integration (`@sentry/nextjs`)
- **Session Replay**: 10% session sample, 100% on error
- **Tunnel route**: `/monitoring` bypasses ad-blockers
- **Error boundaries**: Automatic React error capture
- **Release tracking**: Git SHA from `VERCEL_GIT_COMMIT_SHA`
- **PII enabled**: User context included in events

### MCP Server Integration
- **3 Sentry tools** for admin observability:
  - `instainstru_sentry_issues_top` - List top issues for triage
  - `instainstru_sentry_issue_detail` - Fetch issue metadata + representative event
  - `instainstru_sentry_assign` - Assign issues to team members
- **Error tracking** with git SHA releases

### Celery Beat Monitoring (Sentry Crons)
Critical tasks monitored with check-in/failure thresholds:
- `apply-data-retention-policies` (daily 2 AM)
- `calculate-search-metrics` (hourly)
- `learn-location-aliases` (daily 3:10 AM)
- `resolve-undisputed-no-shows` (hourly)

### Environment Variables

```bash
# Required
SENTRY_DSN=https://...@sentry.io/...    # Sentry DSN

# Optional (auto-detected)
SENTRY_ENVIRONMENT=production           # Environment name
GIT_SHA=...                             # Release version (or RENDER_GIT_COMMIT)

# Frontend specific
NEXT_PUBLIC_SENTRY_DSN=https://...      # Frontend DSN (public)
VERCEL_GIT_COMMIT_SHA=...               # Release from Vercel
```

### Key Files
- [backend/app/monitoring/sentry.py](backend/app/monitoring/sentry.py) - Backend Sentry initialization
- [backend/app/monitoring/sentry_crons.py](backend/app/monitoring/sentry_crons.py) - Celery Beat monitoring config
- [frontend/sentry.client.config.ts](frontend/sentry.client.config.ts) - Client-side config (replay, tunnel)
- [frontend/sentry.server.config.ts](frontend/sentry.server.config.ts) - Server-side config
- [frontend/sentry.edge.config.ts](frontend/sentry.edge.config.ts) - Edge runtime config
- [frontend/app/monitoring/route.ts](frontend/app/monitoring/route.ts) - Error tunnel route
- [mcp-server/src/instainstru_mcp/tools/sentry.py](mcp-server/src/instainstru_mcp/tools/sentry.py) - MCP Sentry tools

---

## OpenTelemetry (Axiom)

### Purpose
Backend distributed tracing with Axiom as the trace/logs backend. Sentry remains for errors only.

### Environment Variables

```bash
# Feature flag
ENABLE_OTEL=true|false

# Service identity
OTEL_SERVICE_NAME=instainstru-api

# OTLP exporter endpoint (Axiom)
OTEL_EXPORTER_OTLP_ENDPOINT=https://api.axiom.co

# Auth headers for Axiom ingest (no spaces around commas)
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer ${AXIOM_API_TOKEN},X-Axiom-Dataset=instainstru-traces

# Sampling
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.5

# Optional (used by init_otel when OTEL_EXPORTER_OTLP_HEADERS not set)
AXIOM_API_TOKEN=...
AXIOM_TRACES_DATASET=instainstru-traces
AXIOM_LOGS_DATASET=instainstru-logs
```

### Key Files
- [backend/app/monitoring/otel.py](backend/app/monitoring/otel.py) - OTel initialization/instrumentation
- [backend/app/middleware/performance.py](backend/app/middleware/performance.py) - X-Trace-ID response header
- [backend/app/errors.py](backend/app/errors.py) - trace_id in error responses

---

## Cloudflare R2

### Purpose
S3-compatible asset storage for user uploads (profile photos, certificates, etc.).

### Integration Flow

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    ┌──────────────┐
│ Upload      │ →  │ Generate     │ →  │ Client uploads  │ →  │ Public URL   │
│ Request     │    │ Presigned URL│    │ directly to R2  │    │ via CDN      │
└─────────────┘    └──────────────┘    └─────────────────┘    └──────────────┘
```

### Features
- SigV4 presigned URL generation (GET/PUT/DELETE)
- Custom domain: `assets.instainstru.com`
- 80% bandwidth reduction via Image Transformations
- No boto3 dependency (minimal client implementation)

### Environment Variables

```bash
# Required
R2_ACCOUNT_ID=...                       # Cloudflare account ID
R2_ACCESS_KEY_ID=...                    # R2 access key
R2_SECRET_ACCESS_KEY=...                # R2 secret key (sensitive)
R2_BUCKET_NAME=...                      # Bucket name

# Optional
R2_ENABLED=true|false                   # Enable/disable R2 (default: true)
R2_PUBLIC_BASE_URL=https://assets.instainstru.com  # Public CDN URL
```

### Key Files
- [backend/app/services/r2_storage_client.py](backend/app/services/r2_storage_client.py) - R2 client
- [backend/app/services/storage_null_client.py](backend/app/services/storage_null_client.py) - Null fallback

---

## Google Maps

### Purpose
Primary geocoding provider and Places autocomplete for address management.

### Integration Flow

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Address     │ →  │ Google Maps  │ →  │ Lat/Lng +       │
│ Input       │    │ Geocoding API│    │ Components      │
└─────────────┘    └──────────────┘    └─────────────────┘

┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Autocomplete│ →  │ Places API   │ →  │ Place Details   │
│ Query       │    │ autocomplete │    │ + Coordinates   │
└─────────────┘    └──────────────┘    └─────────────────┘
```

### Features
- Forward and reverse geocoding
- Places autocomplete with session tokens
- Automatic Mapbox fallback if Google unavailable
- Location biasing for NYC area

### Environment Variables

```bash
# Required
GOOGLE_MAPS_API_KEY=...                 # Google Maps API key

# Configuration
GEOCODING_PROVIDER=google|mapbox|mock   # Provider selection
```

### Key Files
- [backend/app/services/geocoding/google_provider.py](backend/app/services/geocoding/google_provider.py) - Google provider
- [backend/app/services/geocoding/base.py](backend/app/services/geocoding/base.py) - Base interface

---

## Mapbox

### Purpose
Secondary geocoding provider and fallback for Google Maps.

### Environment Variables

```bash
MAPBOX_ACCESS_TOKEN=pk.eyJ...           # Mapbox access token
```

### Key Files
- [backend/app/services/geocoding/mapbox_provider.py](backend/app/services/geocoding/mapbox_provider.py) - Mapbox provider

---

## OpenAI

### Purpose
Natural language search query parsing using GPT-4o-mini for complex queries.

### Integration Flow

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐    ┌──────────────┐
│ Search      │ →  │ Regex Parser │ →  │ OpenAI LLM      │ →  │ Structured   │
│ Query       │    │ (fast path)  │    │ (complex)       │    │ ParsedQuery  │
└─────────────┘    └──────────────┘    └─────────────────┘    └──────────────┘
```

### Features
- Hybrid parsing: regex fast-path (70%+ queries) + LLM for complex
- Circuit breaker for OpenAI failures
- Semaphore for concurrency control
- Strict 2s timeout (fail fast)

### Environment Variables

```bash
# Required (for LLM parsing)
OPENAI_API_KEY=sk-...                   # OpenAI API key

# Configuration
OPENAI_LOCATION_MODEL=gpt-4o-mini       # Model for location resolution
OPENAI_LOCATION_TIMEOUT_MS=3000         # Timeout for location calls
OPENAI_CALL_CONCURRENCY=3               # Max concurrent calls
OPENAI_TIMEOUT_S=2.0                    # General LLM timeout
```

### Key Files
- [backend/app/services/search/llm_parser.py](backend/app/services/search/llm_parser.py) - LLM parser
- [backend/app/services/search/query_parser.py](backend/app/services/search/query_parser.py) - Regex parser
- [backend/app/services/search/circuit_breaker.py](backend/app/services/search/circuit_breaker.py) - Circuit breaker
- [backend/app/services/search/openai_semaphore.py](backend/app/services/search/openai_semaphore.py) - Concurrency control

---

## Redis

### Purpose
Caching, session storage, rate limiting, and Celery message broker.

### Uses
- **Caching**: API responses, permission lookups, search results
- **Rate Limiting**: GCRA algorithm with hot-reload config
- **Celery Broker**: Task queue for background jobs
- **Sessions**: Session token storage
- **Locks**: Distributed locking for critical sections

### Environment Variables

```bash
# Required
REDIS_URL=redis://localhost:6379        # Redis connection URL

# Configuration
CACHE_TTL=3600                          # Default cache TTL (1 hour)
```

### Key Files
- [backend/app/services/cache_service.py](backend/app/services/cache_service.py) - Cache service
- [backend/app/ratelimit/redis_backend.py](backend/app/ratelimit/redis_backend.py) - Rate limit backend
- [backend/app/tasks/celery_app.py](backend/app/tasks/celery_app.py) - Celery configuration

---

## Celery

### Purpose
Distributed task queue for background job processing using Redis as the message broker.

### Architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ FastAPI     │ →  │ Redis        │ →  │ Celery Worker   │
│ Task Enqueue│    │ (broker)     │    │ Task Execution  │
└─────────────┘    └──────────────┘    └─────────────────┘

┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Celery Beat │ →  │ Scheduled    │ →  │ Celery Worker   │
│ (scheduler) │    │ Task Enqueue │    │ Task Execution  │
└─────────────┘    └──────────────┘    └─────────────────┘
```

### Task Categories

| Category | Tasks | Schedule |
|----------|-------|----------|
| **Payments** | Authorization, capture, retry, health check, payout audit | Every 5-60 min |
| **Notifications** | Dispatch pending, booking reminders | Every 15-30 sec |
| **Analytics** | Calculate metrics, daily reports, codebase metrics | 2:30 AM/PM |
| **Search** | Metrics calculation, insights, location alias learning | Hourly/Daily |
| **Privacy** | Data retention, search cleanup, privacy reports | Daily/Weekly |
| **Referrals** | Unlock rewards, instructor payouts | Every 15-60 min |
| **Badges** | Finalize pending badges | Daily 7 AM |
| **Embeddings** | Maintain service embeddings | Hourly at :30 |
| **Retention** | Purge soft-deleted records | Daily 4 AM |

### Beat Schedule Highlights

```python
# Critical financial tasks (high priority)
"process-scheduled-authorizations": every 5 min     # Priority 9
"payment-health-check": every 15 min               # Priority 10 (dead man's switch)
"capture-completed-lessons": hourly                # Priority 7

# Analytics (low priority, off-peak)
"calculate-service-analytics": 2:30 AM/PM          # Priority 3
"generate-daily-analytics-report": 2:30 AM         # Priority 3

# Privacy compliance
"apply-data-retention-policies": 2 AM daily        # Priority 2
"cleanup-search-history": 3 AM daily               # Priority 2
"generate-privacy-report": Sunday 1 AM             # Priority 1
```

### Environment Variables

```bash
# Celery configuration (via REDIS_URL)
CELERY_BROKER_URL=redis://localhost:6379/0         # If separate from cache
CELERY_RESULT_BACKEND=redis://localhost:6379/0     # Task result storage

# Queue configuration
CELERY_RETENTION_QUEUE=maintenance                 # Queue for retention tasks
RETENTION_PURGE_CRON=0 4 * * *                     # Custom purge schedule

# Monitoring
FLOWER_BASIC_AUTH=user:password                    # Flower auth (optional)
```

### Key Files
- [backend/app/tasks/celery_app.py](backend/app/tasks/celery_app.py) - Celery app configuration
- [backend/app/tasks/beat_schedule.py](backend/app/tasks/beat_schedule.py) - Beat schedule (25+ tasks)
- [backend/app/tasks/payment_tasks.py](backend/app/tasks/payment_tasks.py) - Payment processing tasks
- [backend/app/tasks/notification_tasks.py](backend/app/tasks/notification_tasks.py) - Notification tasks
- [backend/app/tasks/analytics.py](backend/app/tasks/analytics.py) - Analytics tasks
- [backend/app/tasks/privacy_tasks.py](backend/app/tasks/privacy_tasks.py) - Privacy compliance tasks
- [backend/app/tasks/search_analytics.py](backend/app/tasks/search_analytics.py) - Search analytics
- [backend/app/tasks/referral_tasks.py](backend/app/tasks/referral_tasks.py) - Referral processing

---

## Supabase (PostgreSQL)

### Purpose
Primary PostgreSQL database with PostGIS and pgvector extensions.

### Features
- **PostGIS**: Spatial queries for location-based search
- **pgvector**: Embedding storage for NL search
- **pg_trgm**: Trigram similarity for fuzzy text search
- **3-tier architecture**: INT/STG/PROD database separation

### Environment Variables

```bash
# Database URLs (use appropriate one for environment)
TEST_DATABASE_URL=postgresql://...      # INT database (default)
STG_DATABASE_URL=postgresql://...       # Staging database
PROD_DATABASE_URL=postgresql://...      # Production database (Supabase)

# Selection flags
USE_STG_DATABASE=true                   # Use staging
USE_PROD_DATABASE=true                  # Use production (requires confirmation)
```

### Key Files
- [backend/app/core/database_config.py](backend/app/core/database_config.py) - Database selection
- [backend/app/database/__init__.py](backend/app/database/__init__.py) - Session management

---

## Render

### Purpose
Backend hosting platform for API server, Celery workers, Redis, and MCP server.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Render (Ohio Region)                         │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │ instainstru-api │    │ instainstru-mcp  │    │ instructly-   │  │
│  │ (Web Service)   │    │ (Web Service)    │    │ flower        │  │
│  │ $25/month       │    │ $7/month         │    │ $7/month      │  │
│  └─────────────────┘    └──────────────────┘    └───────────────┘  │
│           │                      │                      │           │
│           └──────────────────────┼──────────────────────┘           │
│                                  ▼                                   │
│                      ┌──────────────────────┐                       │
│                      │   instructly-redis   │                       │
│                      │   (Private Service)  │                       │
│                      │   $7/month           │                       │
│                      └──────────────────────┘                       │
│                                  ▲                                   │
│           ┌──────────────────────┼──────────────────────┐           │
│           │                      │                      │           │
│  ┌─────────────────┐    ┌──────────────────┐                        │
│  │ instainstru-    │    │ instainstru-     │                        │
│  │ celery (Worker) │    │ celery-beat      │                        │
│  │ $7/month        │    │ $7/month         │                        │
│  └─────────────────┘    └──────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
```

### Services Hosted (~$60/month total)

| Service | Type | Plan | Purpose |
|---------|------|------|---------|
| `instainstru-backend` | Web Service | Standard ($25) | FastAPI server |
| `instainstru-celery` | Background Worker | Starter ($7) | Task processing |
| `instainstru-celery-beat` | Background Worker | Starter ($7) | Task scheduler |
| `instructly-flower` | Web Service | Starter ($7) | Celery monitoring UI |
| `instructly-redis` | Private Service | Starter ($7) | Cache & message broker |
| `instainstru-mcp` | Web Service | Starter ($7) | MCP Admin Copilot |

### Configuration
Infrastructure defined in `render.yaml` at repository root:
- **Region**: Ohio (us-east)
- **Auto-deploy**: Disabled for all services (manual deploys for safety)
- **Health checks**: `/api/v1/health/lite` (API), `/healthcheck` (Flower), `/api/v1/health` (MCP)

### Auto-Injected Environment Variables

```bash
# Render auto-injects these variables
RENDER_GIT_COMMIT=...               # Git SHA (used for Sentry releases)
RENDER_EXTERNAL_URL=...             # Service public URL
RENDER_SERVICE_NAME=...             # Service name
PORT=...                            # Port to bind to
```

### Key Files
- [render.yaml](render.yaml) - Infrastructure-as-code definition
- [redis/Dockerfile](redis/Dockerfile) - Custom Redis image

---

## Vercel

### Purpose
Frontend hosting platform for Next.js application with edge capabilities.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                            Vercel                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Production Environments                     │   │
│  │                                                                │   │
│  │   ┌─────────────────┐        ┌─────────────────┐             │   │
│  │   │ beta.instainstru│        │preview.instainstru│            │   │
│  │   │      .com       │        │       .com       │             │   │
│  │   │  (Main Testing) │        │ (PR Previews)    │             │   │
│  │   └─────────────────┘        └─────────────────┘             │   │
│  │                                                                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Features:                                                           │
│  • Edge Middleware       • Image Optimization                       │
│  • Preview per PR        • Sentry Integration                       │
│  • HSTS Headers          • Immutable Caching                        │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Environments

| Environment | Domain | Purpose |
|-------------|--------|---------|
| **Beta** | `beta.instainstru.com` | Main testing, future production |
| **Preview** | `preview.instainstru.com` | PR previews, stakeholder testing |

**Note**: `instainstru.com` is currently a separate landing page repo. The platform will move to the main domain after beta phase completes.

### Features
- **Preview deployments**: Automatic deployment per PR for testing
- **Edge middleware**: Request routing and header injection
- **Image optimization**: AVIF/WebP format support for R2 assets
- **Sentry tunnel**: `/monitoring` route bypasses ad-blockers
- **Security headers**: HSTS, X-Frame-Options, CSP via `next.config.ts`
- **Immutable caching**: Static assets cached for 1 year

### Configuration
- **`vercel.json`**: HSTS headers configuration
- **`next.config.ts`**: Full Next.js + Sentry configuration

### Environment-Specific Headers
Preview/Beta environments automatically receive:
- `X-Robots-Tag: noindex, nofollow` (prevent indexing)
- `Cache-Control: private, no-store` (no caching)

### Auto-Injected Environment Variables

```bash
# Vercel auto-injects these variables
VERCEL_GIT_COMMIT_SHA=...           # Git SHA (used for Sentry releases)
VERCEL_ENV=...                      # Environment (production/preview/development)
VERCEL_URL=...                      # Deployment URL
```

### Key Files
- [frontend/vercel.json](frontend/vercel.json) - Vercel configuration
- [frontend/next.config.ts](frontend/next.config.ts) - Next.js + Sentry configuration
- [frontend/sentry.client.config.ts](frontend/sentry.client.config.ts) - Sentry client setup

---

## Cloudflare Turnstile

### Purpose
CAPTCHA protection for login after multiple failed attempts.

### Environment Variables

```bash
TURNSTILE_SECRET_KEY=...                # Backend secret key
TURNSTILE_SITE_KEY=...                  # Frontend site key
CAPTCHA_FAILURE_THRESHOLD=3             # Failures before CAPTCHA required
```

### Key Files
- [backend/app/core/login_protection.py](backend/app/core/login_protection.py) - Login rate limiting

---

## Prometheus / Grafana Cloud

### Purpose
Metrics collection, visualization dashboards, and natural language observability via MCP tools.

### Architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ FastAPI     │ →  │ Prometheus   │ →  │ Grafana Cloud   │
│ /metrics    │    │ Scraper      │    │ Dashboards      │
└─────────────┘    └──────────────┘    └─────────────────┘

MCP Admin Interface:
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│ Claude Code │ →  │ MCP Server   │ →  │ Prometheus/     │
│ NL Query    │    │ observability│    │ Grafana API     │
└─────────────┘    └──────────────┘    └─────────────────┘
```

### Metrics Collected
- **HTTP request metrics**: Duration histogram, total requests, status codes
- **Business metrics**: Bookings, payments, user registrations
- **System metrics**: Worker health, queue depths, cache hit rates

### MCP Observability Tools (8 tools)

The MCP server provides semantic metrics queries via natural language:

| Tool | Purpose |
|------|---------|
| `instainstru_grafana_query` | Run any PromQL query |
| `instainstru_grafana_p99` | Get p99 latency |
| `instainstru_grafana_p50` | Get median latency |
| `instainstru_grafana_request_rate` | Get requests per second |
| `instainstru_grafana_error_rate` | Get 5xx error rate |
| `instainstru_grafana_requests_by_endpoint` | Request rate per endpoint |
| `instainstru_grafana_latency_by_endpoint` | Latency per endpoint |
| `instainstru_grafana_slowest_endpoints` | Top 10 slowest endpoints |

### Natural Language Query Aliases

```python
# Supported NL queries → PromQL translations
"p99 latency" → histogram_quantile(0.99, ...)
"request rate" → sum(rate(requests_total[5m]))
"error rate" → sum(5xx) / sum(total)
"slowest endpoints" → topk(10, ...)
```

### Environment Variables

```bash
# Grafana Cloud API
GRAFANA_CLOUD_STACK=...                 # Stack identifier
GRAFANA_CLOUD_API_KEY=...               # API key for queries
GRAFANA_CLOUD_PROMETHEUS_URL=...        # Prometheus data source URL

# Optional Prometheus HTTP API (direct)
PROMETHEUS_HTTP_URL=http://localhost:9090
PROMETHEUS_BEARER_TOKEN=...             # Optional auth token

# Metrics endpoint protection
METRICS_BASIC_AUTH_USER=...             # Basic auth username
METRICS_BASIC_AUTH_PASS=...             # Basic auth password
METRICS_IP_ALLOWLIST=...                # Comma-separated IPs/CIDRs
```

### Key Files
- [backend/app/monitoring/prometheus_metrics.py](backend/app/monitoring/prometheus_metrics.py) - Metrics registry
- [backend/app/middleware/prometheus_middleware.py](backend/app/middleware/prometheus_middleware.py) - Request metrics
- [mcp-server/src/instainstru_mcp/tools/observability.py](mcp-server/src/instainstru_mcp/tools/observability.py) - MCP observability tools
- [mcp-server/src/instainstru_mcp/tools/metrics.py](mcp-server/src/instainstru_mcp/tools/metrics.py) - Metrics dictionary

---

## Environment Variables Summary

### Required for Production

```bash
# Authentication & Security
SECRET_KEY=...                          # JWT signing key
TOTP_ENCRYPTION_KEY=...                 # 2FA secret encryption
BGC_ENCRYPTION_KEY=...                  # Background check PII encryption

# Stripe (Payments)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET_PLATFORM=whsec_...
STRIPE_WEBHOOK_SECRET_CONNECT=whsec_...

# Checkr (Background Checks)
CHECKR_API_KEY=...
CHECKR_WEBHOOK_USER=...
CHECKR_WEBHOOK_PASS=...
CHECKR_ENV=production

# Email & SMS
RESEND_API_KEY=re_...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1...
SMS_ENABLED=true

# Storage
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET_NAME=...

# Geocoding
GOOGLE_MAPS_API_KEY=...
MAPBOX_ACCESS_TOKEN=...                 # Fallback

# Database
PROD_DATABASE_URL=postgresql://...
REDIS_URL=redis://...

# Observability
SENTRY_DSN=https://...@sentry.io/...

# Search (Optional but recommended)
OPENAI_API_KEY=sk-...
```

### Development Defaults

Many services have sensible development defaults:
- `CHECKR_FAKE=true` - Uses FakeCheckr
- `EMAIL_PROVIDER=console` - Logs emails instead of sending
- `SMS_ENABLED=false` - SMS disabled
- `R2_ENABLED=true` - But NullStorageClient used if keys missing
- Database defaults to INT (`instainstru_test`)

---

## Service Health Dependencies

### Critical Path (App Won't Start)
1. PostgreSQL (Supabase) - Database connection required
2. Redis - Cache and Celery broker required

### Graceful Degradation
3. Stripe - Mock mode in development
4. Checkr - FakeCheckr in non-production
5. Resend - Console logging fallback
6. Twilio - Disabled if not configured
7. R2 - NullStorageClient fallback
8. Google Maps - Mapbox fallback, then mock
9. OpenAI - Regex parser fallback
10. Sentry - Disabled if not configured

---

## Webhook Security

### Authentication Methods

| Service | Method | Details |
|---------|--------|---------|
| Stripe | Signature verification | `Stripe-Signature` header + webhook secret |
| Checkr | Basic Auth + HMAC | Basic auth + `X-Checkr-Signature` |

### Webhook URLs (Production)

| Service | URL |
|---------|-----|
| Stripe (Platform) | `https://api.instainstru.com/api/v1/payments/webhooks/stripe` |
| Stripe (Connect) | `https://api.instainstru.com/api/v1/payments/webhooks/stripe` |
| Checkr | `https://api.instainstru.com/api/v1/webhooks/checkr` |

---

## Testing Integrations

### Stripe Testing
- Use Stripe CLI for local webhooks: `stripe listen --forward-to localhost:8000/api/v1/payments/webhooks/stripe`
- Test cards: See Stripe documentation for test card numbers

### Checkr Testing
- Sandbox environment with `CHECKR_ENV=sandbox`
- FakeCheckr client for unit tests (`CHECKR_FAKE=true`)

### Email Testing
- Set `EMAIL_PROVIDER=console` to log emails
- Check logs for email content during development

### SMS Testing
- Set `SMS_ENABLED=false` for development
- Twilio test credentials available for sandbox

---

## Monitoring & Alerts

### Key Metrics to Monitor
- Stripe webhook processing latency
- Checkr webhook success/failure rate
- Email delivery success rate
- Redis connection pool usage
- OpenAI circuit breaker state

### Sentry Integration
- All services report errors to Sentry
- Celery Beat tasks monitored via Sentry Crons
- Request/user context attached to errors
