# InstaInstru API Endpoint Reference

*Last Updated: January 2026 (Session v129)*

## Overview

- **Base URL**: `/api/v1`
- **Total Endpoints**: 333
- **Authentication**: JWT Bearer token (most endpoints)
- **API Docs**: Available at `/docs` (Swagger UI) and `/redoc` (ReDoc)

## Endpoint Categories Summary

| Category | Prefix | Endpoints | Auth Required |
|----------|--------|-----------|---------------|
| Public | `/public` | 5 | No |
| Search | `/search` | 10 | No (public search) |
| Auth | `/auth` | 6 | Mixed |
| Instructors | `/instructors` | 9 | Mixed |
| Instructor Availability | `/instructors/availability` | 15 | Yes |
| Instructor BGC | `/instructors` (bgc) | 7 | Yes |
| Bookings | `/bookings` | 18 | Yes |
| Instructor Bookings | `/instructor-bookings` | 6 | Yes |
| Messages | `/messages` | 8 | Yes |
| Conversations | `/conversations` | 7 | Yes |
| Reviews | `/reviews` | 9 | Mixed |
| Services | `/services` | 8 | No |
| Favorites | `/favorites` | 4 | Yes |
| Addresses | `/addresses` | 10 | Mixed |
| Referrals | `/referrals`, `/r` | 3 | Mixed |
| Instructor Referrals | `/instructor-referrals` | 4 | Yes |
| Account | `/account` | 8 | Yes |
| Password Reset | `/password-reset` | 3 | No |
| Two-Factor Auth | `/2fa` | 6 | Yes |
| Payments | `/payments` | 18 | Yes |
| Uploads | `/uploads` | 3 | Yes |
| Users | `/users` | 4 | Yes |
| Privacy | `/privacy` | 6 | Yes |
| Push Notifications | `/push` | 4 | Yes |
| Notifications | `/notifications` | 6 | Yes |
| Notification Preferences | `/notification-preferences` | 3 | Yes |
| Student Badges | `/students/badges` | 3 | Yes |
| Pricing | `/pricing` | 1 | No |
| Config | `/config` | 2 | No |
| Search History | `/search-history` | 5 | Yes |
| Beta | `/beta` | 13 | Mixed |
| Analytics | `/analytics` | 12 | Yes (admin) |
| Codebase Metrics | `/analytics/codebase` | 8 | Yes (admin) |
| Monitoring | `/monitoring` | 6 | Yes (admin) |
| Alerts | `/monitoring/alerts` | 3 | Yes (admin) |
| Redis Monitor | `/redis` | 7 | Yes (admin) |
| Database Monitor | `/database` | 1 | Yes (admin) |
| Ops/Metrics | `/ops` | 9 | Yes (admin) |
| Health | `/health` | 3 | No |
| Ready | `/ready` | 1 | No |
| Prometheus | `/metrics` | 1 | No |
| SSE | `/sse` | 1 | Yes |
| Gated | `/gated` | 1 | No |
| Internal | `/internal` | 4 | Yes (internal) |
| Webhooks | `/webhooks/checkr` | 1 | No (webhook) |
| Admin | `/admin/*` | ~60 | Yes (admin) |

---

## Public Endpoints (`/api/v1/public`)

Public endpoints that don't require authentication.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/session/guest` | Create guest session for anonymous browsing |
| POST | `/logout` | Clear session cookies |
| GET | `/instructors/{instructor_id}/availability` | Get public instructor availability |
| GET | `/instructors/{instructor_id}/next-available` | Get next available slot for instructor |
| POST | `/referrals/send` | Send referral invitation (public) |

---

## Search (`/api/v1/search`)

Natural language instructor search with hybrid parsing.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Natural language instructor search |
| GET | `/health` | Search system health check |
| GET | `/analytics/metrics` | Search performance metrics |
| GET | `/analytics/popular` | Popular search queries |
| GET | `/analytics/zero-results` | Queries with zero results |
| POST | `/click` | Log search result click (self-learning) |
| GET | `/config` | Get search configuration (admin) |
| PUT | `/config` | Update search configuration (admin) |
| POST | `/config/reset` | Reset search config to defaults (admin) |

---

## Authentication (`/api/v1/auth`)

User authentication and session management.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/register` | Register new user account |
| POST | `/login` | User login (returns JWT) |
| POST | `/login-with-session` | Login with existing session |
| POST | `/change-password` | Change user password |
| GET | `/me` | Get current user with permissions |
| PATCH | `/me` | Update current user profile |

---

## Instructors (`/api/v1/instructors`)

Instructor profiles and management.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/{instructor_id}` | Get instructor profile |
| POST | `/onboard` | Start instructor onboarding |
| GET | `/me` | Get current instructor profile |
| PUT | `/me` | Update instructor profile |
| POST | `/services` | Add service to instructor |
| DELETE | `/services/{service_id}` | Remove service from instructor |
| GET | `/me/stats` | Get instructor statistics |
| GET | `/me/service-areas` | Get instructor service areas |
| GET | `/{instructor_id}/services` | Get instructor's services |

---

## Instructor Availability (`/api/v1/instructors/availability`)

Availability window management for instructors.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/week` | Get weekly availability template |
| POST | `/week` | Update weekly availability template |
| POST | `/copy-week` | Copy availability to another week |
| POST | `/apply-to-date-range` | Apply template to date range |
| POST | `/specific-date` | Create availability for specific date |
| GET | `/` | List availability windows |
| PATCH | `/bulk-update` | Bulk update availability windows |
| PATCH | `/{window_id}` | Update specific window |
| DELETE | `/{window_id}` | Delete availability window |
| GET | `/week/booked-slots` | Get booked slots for week |
| POST | `/week/validate-changes` | Validate proposed changes |
| GET | `/blackout-dates` | List blackout dates |
| POST | `/blackout-dates` | Create blackout date |
| DELETE | `/blackout-dates/{blackout_id}` | Delete blackout date |

---

## Instructor Background Checks (`/api/v1/instructors`)

Checkr background check integration for instructors.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/me/bgc/consent` | Submit BGC consent |
| POST | `/me/bgc/initiate` | Initiate background check |
| GET | `/me/bgc/status` | Get BGC status |
| POST | `/me/bgc/consent/revoke` | Revoke BGC consent |
| POST | `/me/bgc/pre-adverse-acknowledge` | Acknowledge pre-adverse action |
| POST | `/me/bgc/adverse/dispute` | Dispute adverse action |
| POST | `/me/bgc/adverse/accept` | Accept adverse action |

---

## Bookings (`/api/v1/bookings`)

Student booking operations.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/upcoming` | List upcoming bookings |
| GET | `/stats` | Get booking statistics |
| POST | `/check-availability` | Check time slot availability |
| POST | `/send-reminders` | Trigger booking reminders |
| GET | `/` | List all bookings (paginated) |
| POST | `/` | Create new booking |
| GET | `/{booking_id}/preview` | Preview booking details |
| GET | `/{booking_id}/pricing` | Get pricing breakdown |
| GET | `/{booking_id}` | Get booking details |
| PATCH | `/{booking_id}` | Update booking |
| POST | `/{booking_id}/cancel` | Cancel booking |
| POST | `/{booking_id}/reschedule` | Reschedule booking |
| POST | `/{booking_id}/complete` | Mark booking complete |
| POST | `/{booking_id}/no-show` | Report no-show |
| POST | `/{booking_id}/no-show/dispute` | Dispute no-show |
| POST | `/{booking_id}/tip` | Add tip to booking |
| PATCH | `/{booking_id}/notes` | Update booking notes |
| POST | `/{booking_id}/confirm` | Confirm booking |

---

## Instructor Bookings (`/api/v1/instructor-bookings`)

Booking management from instructor perspective.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/upcoming` | List instructor's upcoming bookings |
| GET | `/stats` | Get instructor booking statistics |
| GET | `/today` | Get today's bookings |
| GET | `/{booking_id}` | Get booking details |
| POST | `/{booking_id}/confirm` | Confirm pending booking |
| POST | `/{booking_id}/decline` | Decline booking request |

---

## Messages (`/api/v1/messages`)

Real-time messaging system.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/{conversation_id}` | Get messages in conversation |
| GET | `/{conversation_id}/attachments` | Get conversation attachments |
| GET | `/{conversation_id}/search` | Search messages |
| POST | `/{conversation_id}` | Send message |
| PATCH | `/{conversation_id}/{message_id}` | Edit message |
| DELETE | `/{conversation_id}/{message_id}` | Delete message |
| POST | `/{conversation_id}/{message_id}/reactions` | Add reaction |
| DELETE | `/{conversation_id}/{message_id}/reactions/{emoji}` | Remove reaction |

---

## Conversations (`/api/v1/conversations`)

Conversation management.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | List conversations |
| GET | `/{conversation_id}` | Get conversation details |
| POST | `/` | Create conversation |
| PUT | `/{conversation_id}/read` | Mark conversation as read |
| POST | `/{conversation_id}/archive` | Archive conversation |
| GET | `/typing-indicator` | Get typing status (SSE) |
| POST | `/{conversation_id}/typing` | Send typing indicator |

---

## Reviews (`/api/v1/reviews`)

Review and rating system.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/` | Create review |
| POST | `/{review_id}/helpful` | Mark review helpful |
| POST | `/{review_id}/response` | Instructor response to review |
| GET | `/instructor/{instructor_id}` | Get instructor reviews |
| GET | `/instructor/{instructor_id}/summary` | Get review summary |
| GET | `/instructor/{instructor_id}/can-review` | Check if can review |
| GET | `/student/my-reviews` | Get student's reviews |
| POST | `/student/{review_id}/edit` | Edit review |

---

## Services (`/api/v1/services`)

Service catalog and instructor services.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/categories` | List service categories |
| GET | `/catalog` | List all services |
| POST | `/instructor/add` | Add service to instructor |
| PATCH | `/{service_id}/capabilities` | Update service capabilities |
| GET | `/search` | Search services |
| GET | `/catalog/top-per-category` | Top services per category |
| GET | `/catalog/top-per-category-with-instructors` | Top services with instructors |
| GET | `/catalog/kids-available` | Services available for kids |

---

## Favorites (`/api/v1/favorites`)

Student favorites management.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/{instructor_id}` | Add instructor to favorites |
| DELETE | `/{instructor_id}` | Remove from favorites |
| GET | `/` | List favorites |
| GET | `/check/{instructor_id}` | Check if favorited |

---

## Addresses (`/api/v1/addresses`)

Address management and geocoding.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/zip/is-nyc` | Check if ZIP is in NYC |
| GET | `/me` | List user addresses |
| POST | `/me` | Create address |
| PATCH | `/me/{address_id}` | Update address |
| DELETE | `/me/{address_id}` | Delete address |
| GET | `/me/primary` | Get primary address |
| GET | `/places/autocomplete` | Google Places autocomplete |
| GET | `/places/details` | Get place details |
| PUT | `/instructors/service-areas` | Update instructor service areas |
| GET | `/coverage/bulk` | Get coverage areas (GeoJSON) |
| GET | `/regions/neighborhoods` | List neighborhoods |

---

## Referrals (`/api/v1/referrals`, `/api/v1/r`)

Student referral program (Give $20/Get $20).

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/send` | Send referral invitation |
| GET | `/me` | Get referral ledger |
| POST | `/apply` | Apply referral code |

**Short URL Routes** (`/api/v1/r`):
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/{code}` | Redirect referral link |

---

## Instructor Referrals (`/api/v1/instructor-referrals`)

Instructor referral program with founding status.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/stats` | Get referral statistics |
| GET | `/referred` | List referred instructors |
| GET | `/popup-data` | Get referral popup data |
| GET | `/founding-status` | Get founding instructor status |

---

## Account (`/api/v1/account`)

Account management operations.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/suspend` | Suspend account |
| POST | `/deactivate` | Deactivate account |
| POST | `/reactivate` | Reactivate account |
| GET | `/status` | Get account status |
| GET | `/phone` | Get phone number |
| PUT | `/phone` | Update phone number |
| POST | `/phone/verify` | Request phone verification |
| POST | `/phone/verify/confirm` | Confirm phone verification |

---

## Password Reset (`/api/v1/password-reset`)

Password reset flow (no auth required).

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/request` | Request password reset |
| POST | `/confirm` | Confirm password reset |
| GET | `/verify/{token}` | Verify reset token |

---

## Two-Factor Authentication (`/api/v1/2fa`)

TOTP-based 2FA with backup codes.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/setup/initiate` | Start 2FA setup |
| POST | `/setup/verify` | Verify and enable 2FA |
| POST | `/disable` | Disable 2FA |
| GET | `/status` | Get 2FA status |
| POST | `/regenerate-backup-codes` | Regenerate backup codes |
| POST | `/verify-login` | Verify 2FA during login |

---

## Payments (`/api/v1/payments`)

Stripe Connect payments and earnings.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/connect/onboard` | Start Stripe Connect onboarding |
| GET | `/connect/status` | Get onboarding status |
| POST | `/connect/onboard/refresh` | Refresh onboarding link |
| POST | `/connect/complete` | Complete onboarding |
| POST | `/connect/verification` | Submit verification documents |
| GET | `/connect/dashboard` | Get Stripe dashboard link |
| POST | `/connect/instant-payout` | Request instant payout |
| POST | `/methods` | Add payment method |
| GET | `/methods` | List payment methods |
| DELETE | `/methods/{method_id}` | Remove payment method |
| POST | `/methods/{method_id}/default` | Set default payment method |
| GET | `/earnings` | Get instructor earnings |
| POST | `/intents` | Create payment intent |
| GET | `/intent/{payment_intent_id}/status` | Get payment intent status |
| GET | `/transactions` | Transaction history |
| GET | `/credits` | Get credit balance |
| POST | `/webhooks/stripe` | Stripe webhook handler |

---

## Uploads (`/api/v1/uploads`)

File upload management (Cloudflare R2).

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/r2/signed-url` | Get signed upload URL |
| POST | `/r2/proxy` | Proxy upload through backend |
| POST | `/r2/finalize/profile-picture` | Finalize profile picture upload |

---

## Users (`/api/v1/users`)

User profile operations.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/me/profile-picture` | Update profile picture |
| GET | `/{user_id}/profile-picture-url` | Get profile picture URL |
| GET | `/profile-picture-urls` | Bulk get profile picture URLs |
| DELETE | `/me/profile-picture` | Delete profile picture |

---

## Privacy (`/api/v1/privacy`)

GDPR/privacy compliance operations.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/export/me` | Export user data |
| POST | `/delete/me` | Request data deletion |
| GET | `/statistics` | Privacy statistics (admin) |
| POST | `/retention/apply` | Apply retention policy (admin) |
| GET | `/export/user/{user_id}` | Export user data (admin) |
| POST | `/delete/user/{user_id}` | Delete user data (admin) |

---

## Push Notifications (`/api/v1/push`)

Web push notification management.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/vapid-key` | Get VAPID public key |
| POST | `/subscribe` | Subscribe to push notifications |
| DELETE | `/unsubscribe` | Unsubscribe |
| GET | `/subscriptions` | List subscriptions |

---

## Notifications (`/api/v1/notifications`)

In-app notification management.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | List notifications |
| GET | `/unread-count` | Get unread count |
| POST | `/read-all` | Mark all as read |
| DELETE | `/` | Delete all notifications |
| POST | `/{notification_id}/read` | Mark as read |
| DELETE | `/{notification_id}` | Delete notification |

---

## Notification Preferences (`/api/v1/notification-preferences`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Get preferences |
| PUT | `/` | Update all preferences |
| PUT | `/{category}/{channel}` | Update single preference |

---

## Student Badges (`/api/v1/students/badges`)

Achievement system for students.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | List all badges |
| GET | `/earned` | List earned badges |
| GET | `/progress` | Get badge progress |

---

## Search History (`/api/v1/search-history`)

User search history management.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | List search history |
| POST | `/` | Save search |
| POST | `/save-for-later` | Save search for later |
| DELETE | `/{search_id}` | Delete search entry |
| POST | `/clear` | Clear search history |

---

## Beta Access (`/api/v1/beta`)

Beta invitation and access management.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/invites/validate` | Validate invite code |
| GET | `/invites/code/{code}` | Get invite details |
| POST | `/invites/generate` | Generate invite codes |
| GET | `/metrics/summary` | Beta metrics summary |
| POST | `/invites/consume` | Consume invite code |
| POST | `/invites/send` | Send invite email |
| POST | `/invites/send-batch` | Send batch invites |
| POST | `/invites/send-batch-async` | Start async batch send |
| GET | `/invites/send-batch-progress` | Check batch progress |
| GET | `/settings` | Get beta settings |
| PUT | `/settings` | Update beta settings |

---

## Analytics (`/api/v1/analytics`)

Platform analytics (admin only).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/search/search-trends` | Search trend analysis |
| GET | `/search/popular-searches` | Popular searches |
| GET | `/search/referrers` | Search referrer analysis |
| GET | `/search/search-analytics-summary` | Analytics summary |
| GET | `/search/conversion-metrics` | Conversion metrics |
| GET | `/search/search-performance` | Performance metrics |
| POST | `/export` | Export analytics data |
| GET | `/search/candidates/summary` | Candidate summary |
| GET | `/search/candidates/category-trends` | Category trends |
| GET | `/search/candidates/top-services` | Top services |
| GET | `/search/candidates/queries` | Service queries |

---

## Codebase Metrics (`/api/v1/analytics/codebase`)

Development metrics tracking.

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/metrics` | Get codebase metrics |
| GET | `/history` | Get metrics history |
| POST | `/history/append` | Append to history |
| GET | `/test-counts` | Test counts |
| GET | `/doc-coverage` | Documentation coverage |
| GET | `/type-safety` | Type safety metrics |
| GET | `/architecture` | Architecture metrics |
| GET | `/performance` | Performance metrics |
| GET | `/compliance` | Compliance metrics |

---

## Monitoring (`/api/v1/monitoring`)

System monitoring (admin only).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/dashboard` | Monitoring dashboard |
| GET | `/slow-queries` | Slow database queries |
| GET | `/slow-requests` | Slow HTTP requests |
| GET | `/cache/extended-stats` | Cache statistics |
| POST | `/alerts/acknowledge/{alert_type}` | Acknowledge alert |
| GET | `/payment-health` | Payment system health |
| POST | `/trigger-payment-health-check` | Trigger health check |

---

## Alerts (`/api/v1/monitoring/alerts`)

Alert management (admin only).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/recent` | Recent alerts |
| GET | `/summary` | Alert summary |
| GET | `/live` | Live alert stream |

---

## Redis Monitor (`/api/v1/redis`)

Redis health and management (admin only).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Redis health check |
| GET | `/test` | Redis connectivity test |
| GET | `/stats` | Redis statistics |
| GET | `/celery-queues` | Celery queue stats |
| GET | `/connection-audit` | Connection audit |
| DELETE | `/flush-queues` | Flush Celery queues |

---

## Ops/Metrics (`/api/v1/ops`)

Operational metrics and rate limiting (admin only).

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/performance` | Performance metrics |
| GET | `/performance/detail` | Detailed performance |
| GET | `/database/pool` | Database pool stats |
| GET | `/database/connections` | Connection details |
| GET | `/cache/stats` | Cache statistics |
| POST | `/cache/invalidate` | Invalidate cache |
| GET | `/rate-limiter/stats` | Rate limiter stats |
| POST | `/rate-limiter/reload` | Reload rate limiter config |
| GET | `/rate-limiter/effective-policy` | Get effective policy |

---

## Health & Infrastructure

### Health (`/api/v1/health`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Full health check |
| GET | `/lite` | Lightweight health check |
| GET | `/rate-limit-test` | Test rate limiting |

### Ready (`/api/v1/ready`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Kubernetes readiness probe |

### Prometheus (`/api/v1/metrics`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/prometheus` | Prometheus metrics scrape |

### Gated (`/api/v1/gated`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Check beta gate status |

### SSE (`/api/v1/sse`)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/events` | Server-Sent Events stream |

### Internal (`/api/v1/internal`)
| Method | Path | Purpose |
|--------|------|---------|
| Various | `/metrics/*` | Internal metrics collection |

---

## Webhooks

### Checkr (`/api/v1/webhooks/checkr`)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/` | Checkr webhook receiver |

---

## Admin Endpoints (`/api/v1/admin/*`)

Administrative endpoints requiring admin permissions.

### Admin Config (`/admin/config`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/pricing` | Get pricing config |
| PATCH | `/pricing` | Update pricing config |

### Admin Search Config (`/admin`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/search-config` | Get search config |
| POST | `/search-config` | Update search config |
| POST | `/search-config/reset` | Reset search config |

### Admin Audit (`/admin/audit`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | List audit logs |

### Admin Badges (`/admin/badges`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/{user_id}` | Get user badges |
| POST | `/{user_id}/award` | Award badge |
| POST | `/{user_id}/revoke` | Revoke badge |

### Admin Background Checks (`/admin/background-checks`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/review/count` | Get review count |
| GET | `/review` | List pending reviews |
| GET | `/counts` | Get case counts |
| GET | `/cases` | List all cases |
| GET | `/history/{instructor_id}` | BGC history |
| GET | `/expiring` | Expiring checks |
| GET | `/webhooks` | Webhook logs |
| GET | `/webhooks/stats` | Webhook stats |
| POST | `/{instructor_id}/override` | Override BGC result |
| POST | `/{instructor_id}/dispute/open` | Open dispute |
| POST | `/{instructor_id}/dispute/resolve` | Resolve dispute |
| GET | `/consent/{instructor_id}/latest` | Latest consent |

### Admin Instructors (`/admin/instructors`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/{instructor_id}` | Get instructor details |
| GET | `/founding/count` | Get founding count |

### Admin Auth Blocks (`/admin/auth-blocks`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | List auth issues |
| GET | `/summary` | Summary stats |
| GET | `/{email}` | Get blocked account |
| DELETE | `/{email}` | Clear blocks |

### Admin Location Learning (`/admin/location-learning`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/unresolved` | Unresolved location queries |
| GET | `/pending-aliases` | Pending aliases |
| GET | `/regions` | List regions |
| POST | `/process` | Process learning |
| POST | `/alias/approve` | Approve alias |
| POST | `/alias/reject` | Reject alias |
| POST | `/aliases` | Create alias |
| POST | `/alias/{alias_id}/update` | Update alias |

### Admin Bookings (`/admin`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/bookings/search` | Search bookings |
| GET | `/bookings/stats` | Booking stats |
| GET | `/bookings/{booking_id}` | Get booking |
| GET | `/bookings/instructor/{instructor_id}` | Instructor bookings |
| POST | `/bookings/{booking_id}/force-cancel` | Force cancel |
| POST | `/bookings/{booking_id}/extend` | Extend booking |
| POST | `/bookings/{booking_id}/complete` | Admin complete |

### Admin Refunds (`/admin/bookings`)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/{booking_id}/refund` | Process refund |

### Admin Referrals (`/admin/referrals`)
| Method | Path | Purpose |
|--------|------|---------|
| Various | `/*` | Referral administration |

---

## MCP Admin Endpoints (`/api/v1/admin/mcp/*`)

Model Context Protocol endpoints for AI/LLM tool integration.

### MCP Founding (`/admin/mcp/founding`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/stats` | Founding program stats |
| GET | `/instructors` | List founding instructors |

### MCP Instructors (`/admin/mcp/instructors`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/summary` | Instructor summary |
| GET | `/pending-approval` | Pending approvals |
| GET | `/recently-approved` | Recently approved |

### MCP Invites (`/admin/mcp/invites`)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/create` | Create invite |
| POST | `/send` | Send invite |
| GET | `/list` | List invites |
| GET | `/stats` | Invite statistics |

### MCP Search (`/admin/mcp/search`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/stats` | Search stats |
| GET | `/trends` | Search trends |

### MCP Metrics (`/admin/mcp/metrics`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/overview` | Platform metrics overview |

### MCP Celery (`/admin/mcp/celery`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Celery health |
| GET | `/workers` | Worker status |
| GET | `/tasks/active` | Active tasks |
| GET | `/tasks/scheduled` | Scheduled tasks |
| GET | `/tasks/reserved` | Reserved tasks |
| GET | `/beat/schedule` | Beat schedule |
| GET | `/queues` | Queue stats |

### MCP Operations (`/admin/mcp/ops`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | System health |
| GET | `/database` | Database stats |
| GET | `/cache` | Cache stats |
| GET | `/rate-limiting` | Rate limit stats |
| GET | `/errors/recent` | Recent errors |
| GET | `/performance` | Performance overview |

### MCP Services (`/admin/mcp/services`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/catalog/stats` | Service catalog stats |
| GET | `/popular` | Popular services |

---

## Authentication Requirements Legend

| Symbol | Meaning |
|--------|---------|
| **No** | Public endpoint, no auth required |
| **Yes** | JWT Bearer token required |
| **Mixed** | Some operations require auth |
| **Admin** | Requires admin permissions |
| **Webhook** | External service callback |

---

## Rate Limiting

All endpoints are subject to GCRA rate limiting with the following buckets:

| Bucket | Rate | Burst | Description |
|--------|------|-------|-------------|
| `auth_bootstrap` | 100/min | 20 | Authentication endpoints |
| `read` | 120/min | 20 | Read operations (default) |
| `write` | 30/min | 10 | Write operations, messaging |
| `conv_msg` | 60/min | 10 | Per-conversation messaging |
| `financial` | 5/min | 0 | Payment/booking operations |
| `admin_mcp` | 60/min | 10 | MCP admin endpoints |
| `admin_mcp_invite` | 10/min | 2 | Invite operations |

See [Rate Limiter Documentation](../architecture/02_architecture_state.md) for details.

---

## Related Documentation

- [Architecture State](../architecture/02_architecture_state.md) - System architecture
- [Repository Pattern](../architecture/06_repository_pattern_architecture.md) - Data access patterns
- [System Capabilities](../project-status/04_system-capabilities.md) - Feature overview
