# Project Documentation Index
*Last Updated: January 2026 (Session v129)*

## Quick Reference

| Metric | Value |
|--------|-------|
| Total Tests | 11,485+ |
| API Endpoints | 333 (all `/api/v1/*`) |
| Pass Rate | 100% |
| Load Capacity | 150 concurrent users |
| Infrastructure | $60/month |

## Core Project Docs

| File | Description |
|------|-------------|
| `project-overview/01_core_project_info.md` | Project overview, tech stack, team structure |
| `architecture/02_architecture_state.md` | Service layer, database schema, patterns |
| `project-status/03_work-streams-status.md` | Work streams and progress |
| `project-status/04_system-capabilities.md` | Feature status, known issues |
| `development/testing/05_testing_infrastructure.md` | Test setup, coverage, commands |
| `architecture/06_repository_pattern_architecture.md` | Repository pattern guide |
| `architecture/07_codebase_structure.md` | Monorepo structure, key files, navigation guide |
| `project-overview/08_business_rules.md` | Platform fees, credits, founding program, policies |
| `api/09_api_endpoints.md` | Complete API endpoint reference (333 endpoints) |
| `infrastructure/10_external_integrations.md` | External services (Stripe, Checkr, Sentry, etc.) |
| `architecture/architecture-decisions.md` | ADRs and technical decisions |

## Architecture Documentation

| File | Description |
|------|-------------|
| `architecture/NL-Search-Architecture-Documentation.md` | Complete NL Search system design |
| `architecture/availability-bitmap.md` | Bitmap-based availability system |
| `architecture/location-architecture.md` | PostGIS spatial architecture |
| `architecture/messaging-architecture.md` | Real-time messaging with SSE |
| `architecture/rbac-system-overview.md` | RBAC with 30 permissions |
| `architecture/repository-pattern-implementation.md` | Repository pattern details |
| `architecture/nls-search-behavior-spec.md` | NL Search behavior specification |
| `architecture/quick-reference.md` | Quick reference for common patterns |
| `architecture/new-developer-guide.md` | Onboarding guide for developers |
| `architecture/ARCHITECTURE_AUTH.md` | Authentication architecture |
| `architecture/patterns/middleware-and-caching-technical-solutions-reference.md` | Caching patterns |

## Systems Documentation

| File | Description |
|------|-------------|
| `systems/api-versioning-migration.md` | API v1 migration guide |
| `systems/availability-bitmap-system.md` | Availability bitmap operations |
| `systems/background-check-system.md` | Checkr integration guide |
| `systems/payment-system-architecture.md` | Stripe Connect architecture |
| `systems/rate-limiter-operations.md` | GCRA rate limiter operations |

## API Documentation

| File | Description |
|------|-------------|
| `api/api-standards-guide.md` | Pydantic response model standards |
| `api/api-structure-update.md` | Endpoint structure (all under `/api/v1/*`) |
| `api/instainstru-api-guide.md` | Complete API reference |
| `api/instainstru-openapi.yaml` | OpenAPI specification |
| `api/instainstru-postman.json` | Postman collection |

## Infrastructure Documentation

| File | Description |
|------|-------------|
| `infrastructure/database-safety.md` | 3-tier INT/STG/PROD system |
| `infrastructure/ci-database.md` | Custom CI PostgreSQL image |
| `infrastructure/r2-asset-guide.md` | Cloudflare R2 asset storage |
| `infrastructure/email-configuration.md` | Resend email setup |
| `infrastructure/email-dns-setup.md` | DNS configuration for email |
| `infrastructure/redis-migration-complete.md` | Redis setup and migration |
| `infrastructure/api-url-migration.md` | API URL migration guide |
| `infrastructure/ssl-config-summary.md` | SSL/TLS configuration |

## Development Guides

| File | Description |
|------|-------------|
| `development/setup-guide.md` | Local development setup |
| `development/pre-commit-hooks.md` | Pre-commit hook configuration |
| `development/react-query-patterns.md` | React Query usage patterns |
| `development/timezone-handling.md` | Timezone-aware code patterns |
| `development/testing-patterns-doc.md` | Testing patterns and fixtures |
| `development/testing/rbac-frontend-testing-guide.md` | RBAC testing guide |

## Operations & Runbooks

| File | Description |
|------|-------------|
| `runbooks/local_dev.md` | Local development runbook |
| `runbooks/rate-limiter.md` | Rate limiter configuration |
| `runbooks/rate-limiter-rollout.md` | Rate limiter rollout guide |
| `runbooks/bgc-operations.md` | Background check operations |
| `runbooks/day2-ops.md` | Day 2 operations guide |
| `runbooks/flip_phase_to_open.md` | Phase switching runbook |
| `runbooks/metrics-to-grafana-cloud.md` | Grafana Cloud setup |
| `operations/CELERY_SETUP_GUIDE.md` | Celery worker setup |
| `operations/REDIS_SETUP_GUIDE.md` | Redis setup guide |
| `operations/PRODUCTION_SETUP_GUIDE.md` | Production deployment |
| `deployment/FLOWER_DEPLOYMENT_GUIDE.md` | Flower monitoring setup |
| `deployment/render-health-checks.md` | Render health check config |

## Security Documentation

| File | Description |
|------|-------------|
| `security/authz_matrix.md` | Authorization matrix |
| `security/csrf.md` | CSRF protection guide |
| `security/security-headers.md` | Security headers config |
| `security/public_api_inventory.md` | Public API endpoints |

## Beta/Launch Documentation

| File | Description |
|------|-------------|
| `beta/phase-switch-playbook.md` | Beta phase switching |
| `beta/rollback.md` | Rollback procedures |

## Stripe/Payments

| File | Description |
|------|-------------|
| `stripe/PAYMENT_COMPONENTS.md` | Payment component guide |
| `stripe/INSTRUCTOR_PAYMENT_COMPONENTS.md` | Instructor payment setup |
| `stripe/STRIPE_TEST_SETUP.md` | Stripe test configuration |

## A-Team Deliverables (UX/Design)

| Directory | Contents |
|-----------|----------|
| `a-team-deliverables/` | All UX/Design deliverables |
| `a-team-deliverables/phoenix-week4-designs/` | Homepage, instructor profile, my lessons |
| `a-team-deliverables/instructor-account/` | Instructor onboarding flow |
| `a-team-deliverables/search-results/` | Search results design |

## Engineering Documentation

| File | Description |
|------|-------------|
| `engineering/guardrails.md` | Engineering guardrails |
| `engineering/guardrails_runbook.md` | Guardrails runbook |
| `engineering/bitmap-only-cleanup.md` | Bitmap cleanup guide |

## Session Handoffs

Latest 5 sessions (full history in `session-handoffs/`):

| Session | Key Achievements |
|---------|-----------------|
| v129 | MCP expansion (36 tools), 95%+ coverage, Sentry full-stack, security fixes |
| v128 | MCP Admin Copilot, OAuth2 M2M auth, Principal-based authorization |
| v127 | Location system redesign, inline filters, 3-toggle instructor UI |
| v126 | Test coverage sprint (92% → 95%), frontend coverage boost |
| v125 | Notifications system (email, SMS, push, in-app), phone verification |

## Temporary/Working Docs

| Directory | Description |
|-----------|-------------|
| `temp-logs/` | Working documents, prompts, investigation logs |
| `flows/` | User flow analysis and audits |
| `branches/` | Branch-specific documentation |
