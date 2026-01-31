# InstaInstru Codebase Structure
*Last Updated: January 2026 (Session v129)*

## Overview

InstaInstru is a monorepo containing three main applications: a FastAPI backend, a Next.js frontend, and an MCP admin server. This document provides a quick reference for navigating the codebase.

## Root Directory

```
instructly/
├── backend/              # FastAPI Python backend (2,516+ tests)
├── frontend/             # Next.js TypeScript frontend (8,806+ tests)
├── mcp-server/           # MCP Admin Copilot server (163+ tests)
├── docs/                 # Project documentation
├── monitoring/           # Prometheus/Grafana configuration
├── scripts/              # Root-level utility scripts
├── .github/              # GitHub Actions workflows
├── CLAUDE.md             # AI assistant instructions
├── render.yaml           # Render.com deployment config
└── pytest.ini            # Pytest configuration
```

---

## Backend (`backend/`)

FastAPI application with 333 API endpoints, 17+ repositories, and 95.45% test coverage.

```
backend/
├── app/                  # Main application code
│   ├── api/              # API utilities and dependencies
│   │   └── dependencies/ # FastAPI dependency injection
│   ├── auth/             # Authentication helpers
│   ├── core/             # Core utilities (config, rate limiter, timezone)
│   ├── database/         # Database connection and session management
│   ├── domain/           # Domain logic and validators
│   ├── events/           # Event-driven architecture
│   ├── infrastructure/   # External service integrations
│   │   └── cache/        # Redis caching layer
│   ├── integrations/     # Third-party service clients
│   ├── middleware/       # Request/response middleware
│   ├── models/           # SQLAlchemy ORM models (30+ models)
│   ├── monitoring/       # Prometheus metrics
│   ├── notifications/    # Notification system
│   ├── ratelimit/        # GCRA rate limiting
│   ├── repositories/     # Data access layer (17+ repositories)
│   ├── routes/           # API endpoints
│   │   └── v1/           # All API routes (333 endpoints)
│   │       └── admin/    # Admin-only routes
│   ├── schemas/          # Pydantic request/response models
│   ├── services/         # Business logic (90+ services)
│   │   ├── geocoding/    # Location services
│   │   ├── messaging/    # Real-time messaging
│   │   └── search/       # NL Search system
│   ├── tasks/            # Celery background tasks
│   ├── templates/        # Email templates
│   │   └── email/        # HTML email templates
│   └── utils/            # Shared utilities
├── alembic/              # Database migrations
│   └── versions/         # Migration files
├── scripts/              # Backend-specific scripts
│   ├── data/             # Data management scripts
│   ├── dev/              # Development utilities
│   ├── ops/              # Operations scripts
│   └── seed_data/        # Database seeding
├── tests/                # Test suite
│   ├── unit/             # Pure unit tests (no DB)
│   ├── integration/      # Integration tests
│   ├── load/             # Load testing (Locust)
│   └── fixtures/         # Shared test fixtures
├── config/               # Configuration files
└── typings/              # Type stubs for mypy
```

### Key Backend Files

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI application entry point |
| `app/core/config.py` | Settings and environment variables |
| `app/core/rate_limiter.py` | GCRA rate limiting implementation |
| `app/services/base.py` | BaseService with transaction management |
| `app/repositories/base_repository.py` | BaseRepository abstract class |
| `app/repositories/factory.py` | RepositoryFactory for DI |

---

## Frontend (`frontend/`)

Next.js 16 application with TypeScript strict mode, 270+ services, and 95.08% test coverage.

```
frontend/
├── app/                  # Next.js App Router pages
│   ├── (admin)/          # Admin dashboard pages
│   ├── (auth)/           # Authenticated user pages
│   │   ├── instructor/   # Instructor dashboard
│   │   └── student/      # Student dashboard
│   ├── (public)/         # Public pages (search, profiles)
│   ├── (shared)/         # Shared auth pages (login, signup)
│   ├── api/              # Next.js API routes
│   ├── checkout/         # Checkout flow
│   └── dashboard/        # Dashboard layouts
├── components/           # Reusable UI components
│   ├── availability/     # Availability editing
│   ├── booking/          # Booking flow components
│   ├── calendar/         # Calendar components
│   ├── chat/             # Messaging components
│   ├── forms/            # Form components
│   ├── instructor/       # Instructor-specific components
│   ├── lessons/          # Lesson management
│   ├── messaging/        # Real-time messaging
│   ├── notifications/    # Notification components
│   ├── referrals/        # Referral system UI
│   ├── search/           # Search interface
│   │   └── filters/      # Inline search filters
│   ├── security/         # 2FA components
│   ├── student/          # Student-specific components
│   └── ui/               # Base UI components
├── features/             # Feature modules
│   ├── bookings/         # Booking feature
│   ├── instructor-onboarding/  # Onboarding flow
│   ├── instructor-profile/     # Profile management
│   ├── referrals/        # Referral system
│   ├── shared/           # Shared utilities
│   │   ├── api/          # API client and types
│   │   ├── booking/      # Booking utilities
│   │   └── payment/      # Payment utilities
│   └── student/          # Student features
├── hooks/                # Custom React hooks
│   ├── availability/     # Availability hooks
│   └── queries/          # React Query hooks
├── lib/                  # Core utilities
│   ├── api/              # API client
│   ├── calendar/         # Calendar utilities
│   ├── react-query/      # Query configuration
│   ├── time/             # Time utilities
│   └── timezone/         # Timezone handling
├── contexts/             # React contexts
├── providers/            # Context providers
├── services/             # Legacy service layer
│   └── api/              # API services
├── src/                  # Source modules
│   ├── api/              # API layer
│   │   ├── generated/    # Auto-generated API types
│   │   ├── hooks/        # API hooks
│   │   └── services/     # API services
│   └── types/            # TypeScript types
├── types/                # Shared type definitions
│   └── api/              # API response types
├── utils/                # Utility functions
├── e2e/                  # Playwright E2E tests
│   ├── fixtures/         # Test fixtures
│   ├── pages/            # Page objects
│   └── tests/            # Test files
├── __tests__/            # Jest unit tests
└── public/               # Static assets
```

### Key Frontend Files

| File | Purpose |
|------|---------|
| `app/layout.tsx` | Root layout with providers |
| `lib/api/index.ts` | API client configuration |
| `lib/react-query/queryClient.ts` | React Query setup |
| `features/shared/api/types.ts` | API type shim (use this, not generated) |
| `tsconfig.json` | TypeScript strictest configuration |

---

## MCP Server (`mcp-server/`)

FastMCP-based admin copilot with 36 tools, OAuth2 M2M auth, and 100% test coverage.

```
mcp-server/
├── src/
│   └── instainstru_mcp/  # Main package
│       ├── clients/      # HTTP clients for backend/Grafana
│       ├── oauth/        # OAuth2 M2M authentication
│       └── tools/        # MCP tool modules (36 tools)
│           ├── celery.py       # Worker monitoring (7 tools)
│           ├── metrics.py      # PromQL queries (8 tools)
│           ├── observability.py # Grafana integration (8 tools)
│           ├── sentry.py       # Error tracking (4 tools)
│           ├── operations.py   # Admin operations (6 tools)
│           └── ...             # Other tool modules
├── tests/                # Test suite
│   └── oauth/            # OAuth2 tests
└── typings/              # Type stubs
```

### MCP Tool Modules

| Module | Tools | Purpose |
|--------|-------|---------|
| `celery.py` | 7 | Worker status, queue depth, failed tasks |
| `metrics.py` | 8 | PromQL queries, semantic metrics |
| `observability.py` | 8 | Grafana dashboards, alerts, silences |
| `sentry.py` | 4 | Error tracking, issue details |
| `operations.py` | 6 | Bookings, payments, user lookup |
| `invites.py` | 4 | Invite preview/send workflow |
| `instructors.py` | 3 | Instructor management |
| `founding.py` | 2 | Founding funnel summary |
| `services.py` | 1 | Service catalog |
| `search.py` | 2 | Search analytics |

---

## Documentation (`docs/`)

```
docs/
├── README.md             # Documentation index
├── PROJECT_DOCS_INDEX.md # Full doc tree
├── project-overview/     # Core project info
│   └── 01_core_project_info.md
├── architecture/         # Technical architecture
│   ├── 02_architecture_state.md
│   ├── 06_repository_pattern_architecture.md
│   └── architecture-decisions.md
├── project-status/       # Current state
│   ├── 03_work-streams-status.md
│   └── 04_system-capabilities.md
├── development/          # Development guides
│   └── testing/
│       └── 05_testing_infrastructure.md
├── session-handoffs/     # Session history (v1-v129)
├── a-team-deliverables/  # UX designs and specs
├── api/                  # API documentation
├── infrastructure/       # Infrastructure docs
├── operations/           # Operations guides
├── runbooks/             # Incident runbooks
├── security/             # Security documentation
└── stripe/               # Payment documentation
```

---

## CI/CD (`.github/workflows/`)

```
.github/
├── workflows/
│   ├── ci.yml              # Main CI pipeline
│   ├── backend-ci.yml      # Backend tests + coverage
│   ├── e2e-tests.yml       # Playwright E2E tests
│   ├── env-contract.yml    # Environment verification
│   ├── deploy.yml          # Render deployment
│   ├── load-test.yml       # Load testing
│   ├── database-backup.yml # Automated backups
│   └── ...                 # Other workflows
└── docker/
    └── postgres-ci/        # CI database image (PostGIS + pgvector)
```

---

## Monitoring (`monitoring/`)

```
monitoring/
├── prometheus/           # Prometheus configuration
├── grafana/              # Grafana dashboards
├── alertmanager/         # Alert routing
├── terraform/            # Infrastructure as code
└── *.sh                  # Start/stop scripts
```

---

## Configuration Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | AI assistant project context |
| `pytest.ini` | Pytest configuration |
| `render.yaml` | Render.com service definitions |
| `.pre-commit-config.yaml` | Pre-commit hooks (repo pattern, timezone) |
| `codecov.yml` | Code coverage configuration |
| `package.json` | Root workspace (Husky, lint-staged) |

---

## Quick Navigation

### Where to Find...

| Need | Location |
|------|----------|
| API endpoints | `backend/app/routes/v1/` |
| Business logic | `backend/app/services/` |
| Database queries | `backend/app/repositories/` |
| Database models | `backend/app/models/` |
| Pydantic schemas | `backend/app/schemas/` |
| React components | `frontend/components/` |
| Page routes | `frontend/app/` |
| API types | `frontend/features/shared/api/types.ts` |
| React Query hooks | `frontend/hooks/queries/` |
| MCP tools | `mcp-server/src/instainstru_mcp/tools/` |
| Session history | `docs/session-handoffs/` |
| Architecture docs | `docs/architecture/` |

### Key Patterns

- **All IDs are ULIDs** (26-character strings, not integers)
- **All routes under `/api/v1/*`** (single version rule)
- **Repository pattern enforced** via pre-commit hooks
- **React Query mandatory** for all data fetching
- **TypeScript strictest mode** with zero errors
