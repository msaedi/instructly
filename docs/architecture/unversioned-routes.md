# Intentionally Unversioned Routes

This document describes API routes that are intentionally NOT versioned under `/api/v1/*`. These routes remain at fixed paths because external services depend on them or they serve internal admin/ops purposes.

## Route Categories

### Category 1: Infrastructure Routes (External Dependencies)

These routes MUST remain at fixed paths. Changing them would break external service integrations.

| Route | Path | Dependent Service | Protection | Notes |
|-------|------|-------------------|------------|-------|
| Health | `/health` | Load balancers | None (public) | Standard health check endpoint |
| Health (API) | `/api/health` | API clients | None (public) | Health check with API prefix |
| Health Lite | `/health/lite` | Internal probes | None (public) | Lightweight check (no DB) |
| Ready | `/ready` | Kubernetes | None (public) | Readiness probe for pods |
| Prometheus | `/metrics/prometheus` | Prometheus | None (public) | Standard metrics scraping endpoint |
| Gated Probe | `/v1/gated/ping` | CI smoke tests | Beta phase check | Already v1 versioned |

**DO NOT** change these paths without updating:
- Render.com health check configurations
- Kubernetes deployment manifests
- Prometheus scraping configurations
- CI/CD workflow files

### Category 2: Admin Ops/Monitoring Routes (Internal Admin)

These routes serve the internal admin dashboard and ops tools. They are NOT part of the public API contract.

| Route | Path | Protection | Purpose |
|-------|------|------------|---------|
| Performance Metrics | `/ops/*` | Admin role | Internal performance metrics |
| Monitoring Dashboard | `/api/monitoring/*` | API key | Production monitoring |
| Alerts | `/api/monitoring/alerts/*` | API key | Alert management |
| Config Reload | `/internal/*` | HMAC signature | Hot-reload configuration |

**Why not versioned:**
1. These are strictly admin-only routes
2. They require special authentication (API keys, HMAC)
3. They're not part of the public API contract
4. No frontend consumers depend on their paths
5. They are internal ops tools, not application features

### Category 3: Webhook Redirects (External Service Callbacks)

| Route | Path | Redirects To | Notes |
|-------|------|--------------|-------|
| Stripe Webhook | `/api/webhooks/stripe` | `/api/v1/payments/webhooks/stripe` | Backward compatibility |
| Stripe Legacy | `/api/payments/webhooks/stripe` | `/api/v1/payments/webhooks/stripe` | Backward compatibility |

These redirects exist for backward compatibility with webhooks that may still be configured at legacy paths in external service dashboards (Stripe).

### Category 4: Special Routes

| Route | Path | Notes |
|-------|------|-------|
| Referral Short URLs | `/r/{slug}` | Short URL redirects for sharing - not versioned by design |
| Root | `/` | API info endpoint |

## Migration Decisions

### Routes Migrated to v1 (Phases 0-23)

All public-facing application routes have been migrated to `/api/v1/*`:
- Authentication (`/api/v1/auth/*`)
- Users & Profiles (`/api/v1/users/*`)
- Instructors (`/api/v1/instructors/*`)
- Bookings (`/api/v1/bookings/*`)
- Payments (`/api/v1/payments/*`)
- Messages (`/api/v1/messages/*`)
- Search (`/api/v1/search/*`)
- And 25+ more routers...

### Routes Migrated to v1 (Phase 24.5)

The following admin routes were migrated to v1 because they have frontend consumers in the admin dashboard:

| Old Path | New Path | Protection | Frontend Consumer |
|----------|----------|------------|-------------------|
| `/api/analytics/*` | `/api/v1/analytics/*` | VIEW_SYSTEM_ANALYTICS | `lib/analyticsApi.ts` |
| `/api/analytics/codebase/*` | `/api/v1/analytics/codebase/*` | VIEW_SYSTEM_ANALYTICS | `hooks/useCodebaseMetrics.ts` |
| `/api/redis/*` | `/api/v1/redis/*` | ACCESS_MONITORING | `lib/redisApi.ts` |
| `/api/database/*` | `/api/v1/database/*` | ACCESS_MONITORING | `lib/databaseApi.ts` |
| `/api/beta/*` | `/api/v1/beta/*` | Admin role | `lib/betaApi.ts`, signup/join pages |

**Why migrated:**
1. These routes have frontend consumers that need consistent API versioning
2. The admin dashboard is a first-party application that should follow the same API contracts
3. Ensures all frontend code can rely on v1 paths for consistency

### Routes Kept Unversioned (Phase 24)

The following routes were evaluated and intentionally kept unversioned:

1. **Infrastructure routes** - External services depend on fixed paths
2. **Admin/ops routes** - Internal tools only, not public API
3. **Webhook redirects** - Backward compatibility with external configs

## Security Considerations

All unversioned admin routes have appropriate protection:

- **API Key Protected**: Monitoring, alerts - require `X-API-Key` or `X-Monitoring-API-Key` header
- **HMAC Protected**: Internal config - require valid `X-Config-Reload-Signature`
- **Permission Protected**: Analytics, Redis, Database - require specific RBAC permissions
- **Admin Role**: Beta management - requires admin user role

## Adding New Routes

When adding new routes, follow this decision framework:

1. **Will external services (LB, K8s, Prometheus) depend on this?**
   - YES → Keep unversioned, document in this file
   - NO → Continue to step 2

2. **Is this a public API consumed by the frontend or third parties?**
   - YES → Add to `/api/v1/*` with proper versioning
   - NO → Continue to step 3

3. **Is this an internal admin/ops tool?**
   - YES → Keep unversioned under `/api/*` or `/internal/*`
   - NO → Add to `/api/v1/*`

## References

- `backend/app/main.py` - Route registration with inline documentation
- `.github/workflows/ci.yml` - CI health check configuration
- Render Dashboard - Production health check settings
