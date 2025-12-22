[![Env-contract](https://github.com/msaedi/instructly/actions/workflows/env-contract.yml/badge.svg)](https://github.com/msaedi/instructly/actions/workflows/env-contract.yml)
[![Schemathesis](https://github.com/msaedi/instructly/actions/workflows/schemathesis.yml/badge.svg)](https://github.com/msaedi/instructly/actions/workflows/schemathesis.yml)

# InstaInstru

The "Uber of instruction" - A marketplace platform for instantly booking private instructors in NYC.

**Platform Status**: 100% Complete | **Tests**: 3,090+ | **Load Tested**: 150 users | **API**: 235 endpoints

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | FastAPI + PostgreSQL 17 (Supabase) + SQLAlchemy 2.0 |
| **Frontend** | Next.js 15 + TypeScript (strictest) + Tailwind CSS v4 |
| **Cache** | Redis (caching + Celery broker) |
| **Search** | pgvector + pg_trgm (NL Search with self-learning) |
| **Payments** | Stripe Connect (pre-auth, payouts, credits) |
| **Email** | Resend API |
| **Infrastructure** | Render ($53/mo) + Vercel + Cloudflare R2 |
| **Security** | Argon2id, JWT+RBAC (30 permissions), 2FA (TOTP) |

## Quick Start

### Database Setup

```bash
# Defaults to INT database (safe)
python backend/scripts/prep_db.py --migrate --seed-all

# Staging (local dev)
python backend/scripts/prep_db.py stg --migrate --seed-all

# Preview environment
python backend/scripts/prep_db.py preview --migrate --seed-all

# Production (requires confirmation)
SITE_MODE=prod python backend/scripts/prep_db.py --migrate --seed-system-only --force --yes
```

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # Edit with your values
alembic upgrade head
uvicorn app.main:app --reload
```

### Frontend Setup

```bash
cd frontend
npm install
cp .env.local.example .env.local  # Edit with your values
npm run dev
```

### Redis Setup

```bash
docker-compose up -d
```

## Test Accounts

After seeding (Password: `Test1234`):
- **Instructors**: sarah.chen@example.com, michael.rodriguez@example.com
- **Students**: john.smith@example.com, emma.johnson@example.com

## Testing

```bash
# Backend (3,090+ tests)
cd backend && pytest tests/ -v

# Frontend
cd frontend && npm test

# E2E (requires dev servers)
cd frontend && CI_LOCAL_E2E=1 npx playwright test --project=instructor
```

## API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **All endpoints under `/api/v1/*`** (235 total)

## Project Structure

```
instructly/
├── backend/
│   ├── app/
│   │   ├── routes/v1/    # All API endpoints (versioned)
│   │   ├── services/     # Business logic (17+ services)
│   │   ├── repositories/ # Data access (17+ repositories)
│   │   ├── models/       # Database models
│   │   └── schemas/      # Pydantic schemas
│   └── tests/            # 2,600+ backend tests
├── frontend/
│   ├── app/              # Next.js 15 App Router
│   ├── features/         # Feature modules
│   ├── components/       # Shared React components
│   └── e2e/              # Playwright E2E tests
├── docs/                 # Comprehensive documentation
│   └── PROJECT_DOCS_INDEX.md  # Documentation index
└── docker-compose.yml    # Redis setup
```

## Key Features

- **Instant Booking**: No approval process, book directly
- **NL Search**: Natural language search with typo tolerance
- **Bitmap Availability**: Efficient scheduling (70% storage reduction)
- **Founding Instructors**: Lifetime 8% platform fee for early adopters
- **Real-time Messaging**: SSE-based with archive/trash
- **Background Checks**: Checkr integration with adverse action workflow
- **Rate Limiting**: GCRA algorithm with runtime configuration

## Documentation

See `docs/PROJECT_DOCS_INDEX.md` for complete documentation map including:
- Architecture decisions and patterns
- System documentation (payments, search, rate limiting)
- Runbooks and operations guides
- API documentation and standards

## CI/CD

- **Custom CI Database**: PostgreSQL 14 with PostGIS + pgvector
  - Image: `ghcr.io/msaedi/instructly-ci-postgres:14-postgis-pgvector`
- **GitHub Actions**: Automated testing, type-checking, security scans
- **Pre-commit Hooks**: Repository pattern, timezone checks

## Deployment

- **Backend**: Deploy to Render using `render.yaml`
- **Frontend**: Deploy to Vercel via GitHub integration
- **Environments**: Preview (preview.instainstru.com) + Beta (beta.instainstru.com)

## Monitoring

```bash
# Start monitoring stack
./monitoring/start-monitoring.sh

# Access
# Grafana: http://localhost:3003
# Prometheus: http://localhost:9090
```

## License

Copyright 2024 InstaInstru. All rights reserved.
