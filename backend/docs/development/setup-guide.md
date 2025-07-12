# Local Development Setup Guide

This guide walks you through setting up the InstaInstru development environment on your local machine.

## Prerequisites

- Python 3.9 or higher
- Node.js 18 or higher
- Docker and Docker Compose
- PostgreSQL 14 or higher (or use Docker)
- Git

## Quick Start

If you want to get up and running quickly:

```bash
# Clone the repository
git clone <repository-url>
cd instructly

# Run the setup script (if available)
./scripts/setup-dev.sh
```

## Manual Setup

### 1. PostgreSQL Database

#### Option A: Using Docker (Recommended)
```bash
# Run PostgreSQL in Docker
docker run --name instructly-postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=instructly_dev \
  -p 5432:5432 \
  -d postgres:14
```

#### Option B: Local PostgreSQL Installation
```bash
# macOS
brew install postgresql@14
brew services start postgresql@14

# Ubuntu/Debian
sudo apt update
sudo apt install postgresql-14 postgresql-contrib

# Create database and user
sudo -u postgres psql
CREATE DATABASE instructly_dev;
CREATE USER postgres WITH PASSWORD 'postgres';
GRANT ALL PRIVILEGES ON DATABASE instructly_dev TO postgres;
\q
```

### 2. DragonflyDB (Redis-compatible cache)

```bash
# Navigate to project root
cd instructly

# Start DragonflyDB using Docker Compose
docker-compose up -d

# Verify it's running
docker ps | grep dragonfly
# Should show container running on port 6379
```

### 3. Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create Python virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
# venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Create environment file
cp .env.example .env

# Edit .env file with your settings
# Key variables to update:
# - DATABASE_URL=postgresql://postgres:postgres@localhost/instructly_dev
# - REDIS_URL=redis://localhost:6379/0
# - SECRET_KEY=<generate-a-secure-key>
# - RESEND_API_KEY=<your-resend-api-key>
```

### 4. Database Migrations

```bash
# Ensure you're in the backend directory with venv activated
cd backend
source venv/bin/activate

# Run database migrations
alembic upgrade head

# Seed the database with test data
python scripts/reset_and_seed_database_enhanced.py

# Verify database setup
python -c "from app.database import engine; print('Database connected successfully!')"
```

### 5. Frontend Setup

```bash
# Open new terminal and navigate to frontend
cd frontend

# Install Node dependencies
npm install

# Create environment file
cp .env.local.example .env.local

# Edit .env.local file
# Key variables:
# - NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 6. SSL/HTTPS Setup (Optional but Recommended)

```bash
# Generate self-signed certificates for local HTTPS
cd backend
mkdir -p certs
openssl req -x509 -newkey rsa:4096 -nodes \
  -out certs/cert.pem \
  -keyout certs/key.pem \
  -days 365 \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
```

## Running the Application

### Start all services:

```bash
# Terminal 1: Ensure DragonflyDB is running
docker-compose up -d

# Terminal 2: Start backend
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3: Start frontend
cd frontend
npm run dev
```

### Access the application:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs
- Alternative API Docs: http://localhost:8000/redoc

## Verification Checklist

1. **Backend Health Check**
   ```bash
   curl http://localhost:8000/health
   # Should return: {"status": "healthy", "database": "connected", "cache": "connected"}
   ```

2. **Database Connection**
   ```bash
   cd backend
   source venv/bin/activate
   python -c "from app.database import SessionLocal; db = SessionLocal(); print('✅ Database connected')"
   ```

3. **Cache Connection**
   ```bash
   docker exec -it instructly_dragonfly_1 redis-cli ping
   # Should return: PONG
   ```

4. **Test Accounts** (after seeding)
   - Instructors:
     - sarah.chen@example.com
     - michael.rodriguez@example.com
   - Students:
     - john.smith@example.com
     - emma.johnson@example.com
   - Password for all: `TestPassword123!`

## Common Issues and Solutions

### Port Already in Use
```bash
# Find process using port 8000
lsof -i :8000
# Kill the process
kill -9 <PID>

# Or use different port
uvicorn app.main:app --reload --port 8001
```

### Database Connection Failed
- Check PostgreSQL is running: `pg_isready`
- Verify credentials in .env file
- Check DATABASE_URL format: `postgresql://user:password@localhost/database`

### Module Import Errors
```bash
# Ensure virtual environment is activated
which python
# Should show: /path/to/backend/venv/bin/python

# Reinstall dependencies
pip install -r requirements.txt
```

### DragonflyDB Connection Issues
```bash
# Restart Docker containers
docker-compose down
docker-compose up -d

# Check logs
docker-compose logs dragonfly
```

## Development Workflow

1. **Before starting work:**
   ```bash
   # Pull latest changes
   git pull origin main

   # Update dependencies
   cd backend && pip install -r requirements.txt
   cd ../frontend && npm install

   # Run migrations
   cd backend && alembic upgrade head
   ```

2. **Running tests:**
   ```bash
   # Backend tests
   cd backend
   pytest
   pytest -m unit  # Unit tests only
   pytest -m integration  # Integration tests only

   # Frontend tests
   cd frontend
   npm test
   ```

3. **Code quality checks:**
   ```bash
   # Backend
   cd backend
   black .  # Format code
   isort .  # Sort imports

   # Frontend
   cd frontend
   npm run lint
   ```

## Additional Resources

- [API Documentation](/backend/docs/api/instainstru-api-guide.md)
- [Architecture Overview](/backend/docs/architecture/architecture-decisions.md)
- [Testing Guide](/backend/docs/development/testing/)
- [SSL Configuration](/backend/docs/infrastructure/ssl-config-summary.md)

## Getting Help

- Check the [troubleshooting guide](./troubleshooting.md)
- Review recent commits for setup changes
- Consult CLAUDE.md for project-specific context
