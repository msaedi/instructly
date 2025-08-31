## DB prep quickstart

Use `backend/scripts/prep_db.py` with SITE_MODE:

```bash
# Defaults to int
python backend/scripts/prep_db.py --migrate --dry-run

# Local/staging
python backend/scripts/prep_db.py stg --migrate --seed-all

# Preview (system+mock allowed)
python backend/scripts/prep_db.py preview --migrate --seed-all

# Production (system-only, requires --force and --yes)
SITE_MODE=prod python backend/scripts/prep_db.py --migrate --seed-system-only --force --yes
```

# InstaInstru

The "Uber of instruction" - A marketplace platform for instantly booking private instructors in NYC.

## 🚀 Tech Stack

- **Backend**: FastAPI + PostgreSQL (Supabase) + SQLAlchemy
- **Frontend**: Next.js 14 + TypeScript + Tailwind CSS
- **Cache**: DragonflyDB (local) + Upstash Redis (production)
- **Email**: Resend API
- **Infrastructure**: Render Standard plan (backend) + Vercel (frontend)
- **Monitoring**: Custom production monitoring middleware

## 📋 Prerequisites

- Python 3.9+
- Node.js 18+
- PostgreSQL or Supabase account
- Redis/DragonflyDB
- Resend API key for emails

## 🛠️ Setup

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env
# Edit .env with your values

# Run database migrations
alembic upgrade head

# Seed database (optional)
python scripts/reset_and_seed_database_enhanced.py

# Start the server
uvicorn app.main:app --reload
```
### Frontend Setup
```bash
cd frontend
npm install

# Copy environment variables
cp .env.local.example .env.local
# Edit .env.local with your values

# Start the development server
npm run dev

```
### Cache Setup (DragonflyDB)
```bash
# Using Docker
docker-compose up -d

# Or install locally
# See: https://dragonflydb.io/docs/getting-started

```
## 📊 Monitoring

InstaInstru includes a comprehensive monitoring stack with Prometheus and Grafana.

### Quick Start
```bash
# Start monitoring stack
./monitoring/start-monitoring.sh

# Stop monitoring stack
./monitoring/stop-monitoring.sh
```

### Access Points
- **Grafana**: http://localhost:3003 - Dashboards and alerts
- **Prometheus**: http://localhost:9090 - Metrics explorer

### What's Being Monitored
- 98 service operations tracked with `@measure_operation` decorators
- 5 production-ready alert rules (response time, error rate, etc.)
- 3 pre-configured dashboards (Service Performance, API Health, Business Metrics)

See [monitoring/README.md](monitoring/README.md) for detailed setup and configuration.

🧪 Testing
```bash
# Backend tests
cd backend
pytest tests/ -v

# Frontend tests
cd frontend
npm test

```
📚 API Documentation
Once the backend is running, visit:

Swagger UI: http://localhost:8000/docs
ReDoc: http://localhost:8000/redoc

🔑 Default Test Accounts
After seeding the database:

Instructors: sarah.chen@example.com, michael.rodriguez@example.com
Students: john.smith@example.com, emma.johnson@example.com
Password: TestPassword123!

🏗️ Project Structure

instructly/
├── backend/
│   ├── app/
│   │   ├── routes/      # API endpoints
│   │   ├── services/    # Business logic
│   │   ├── models/      # Database models
│   │   └── schemas/     # Pydantic schemas
│   └── tests/
├── frontend/
│   ├── app/            # Next.js app directory
│   ├── components/     # React components
│   ├── lib/           # Utilities
│   └── types/         # TypeScript types
└── docker-compose.yml  # DragonflyDB setup

## 🚀 Production Configuration

### Performance Optimizations
- **Database Pooling**: Optimized for Render Standard (5 connections)
- **Upstash Redis**: Auto-pipelining reduces API calls by 70%
- **Response Times**: <100ms achieved with production monitoring
- **Monitoring**: API key protected endpoints at `/api/monitoring/*`

### CI/CD Infrastructure
- **Custom Database Image**: PostgreSQL 14 with PostGIS + pgvector
  - Required for spatial features and NL search testing
  - Image: `ghcr.io/msaedi/instructly-ci-postgres:14-postgis-pgvector`
  - See [CI Database Documentation](docs/infrastructure/ci-database.md)
- **GitHub Actions**: Automated testing on all PRs
- **Pre-commit Hooks**: Code quality enforcement

### Deployment
- **Backend**: Deploy to Render using `render.yaml`
- **Frontend**: Deploy to Vercel via GitHub integration
- **Environment Variables**: Set all production configs on platforms

See `docs/infrastructure/` for detailed deployment instructions.

#### Cloudflare + Vercel DNS (Admin/Beta)

- Set Cloudflare DNS records to DNS-only (gray cloud) so Vercel serves traffic directly.
- Avoid reverse proxy through Cloudflare to prevent TLS/proxy issues and unexpected caching.

#### Admin Navigation Map

Left sidebar groups:

- Analytics: `/admin/analytics/search`, `/admin/analytics/candidates`
- Ops: `/admin/ops/redis`, `/admin/ops/database`
- Engineering: `/admin/engineering/codebase`
- Beta: `/admin/beta/invites`, `/admin/beta/ui-preview`


📝 License
Copyright © 2024 InstaInstru. All rights reserved.

```bash
### 4. **Pre-commit Hooks**

Pre-commit hooks run checks before each commit. Create `.pre-commit-config.yaml`:

```yaml
# .pre-commit-config.yaml
repos:
  # Python
  - repo: https://github.com/psf/black
    rev: 23.3.0
    hooks:
      - id: black
        files: ^backend/

  - repo: https://github.com/PyCQA/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        files: ^backend/
        args: ['--max-line-length=100']

  # TypeScript/JavaScript
  - repo: https://github.com/pre-commit/mirrors-prettier
    rev: v3.0.0
    hooks:
      - id: prettier
        files: ^frontend/
        types_or: [javascript, jsx, ts, tsx, css, json]

  # General
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
