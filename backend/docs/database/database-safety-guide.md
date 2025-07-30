# Database Safety System Guide

## Overview

InstaInstru uses a three-tier database safety system to prevent accidental data loss and ensure safe development practices. This guide explains how to use the system effectively.

## 🎯 Quick Reference

### Which Database Am I Using?
```bash
python -c "from app.core.config import settings; print(settings.database_url)"
```

### Common Commands
```bash
# Local development (uses STG automatically)
./run_backend.py

# Run tests (uses INT automatically)
pytest

# Database operations (default to INT)
python scripts/prep_db.py
alembic upgrade head
```

## 🛡️ Three-Tier Database Architecture

### 1. INT (Integration Test Database) 🟢
- **Purpose**: Safe testing environment
- **Default**: Yes - all operations default here
- **Can be dropped**: Yes - freely reset for tests
- **Database name**: `instainstru_test`
- **When to use**: Running tests, trying dangerous operations

### 2. STG (Staging/Local Development) 🟡
- **Purpose**: Local development with persistent data
- **Default**: No - requires `USE_STG_DATABASE=true`
- **Can be dropped**: Yes, but preserves data between sessions
- **Database name**: `instainstru_stg`
- **When to use**: Daily development work

### 3. PROD (Production Database) 🔴
- **Purpose**: Live user data
- **Default**: No - requires `USE_PROD_DATABASE=true` + confirmation
- **Can be dropped**: NEVER!
- **Database**: Supabase PostgreSQL
- **When to use**: Production deployments only

## 🚀 Getting Started

### First Time Setup

1. **Create your `.env` file**:
```bash
cp .env.example .env
# Edit .env with your database URLs
```

2. **Create and prepare databases**:
```bash
# Create INT database
python scripts/prep_db.py int

# Create STG database
python scripts/prep_db.py stg
```

3. **Start development**:
```bash
# These scripts automatically use STG
./run_backend.py
./run_celery_worker.py
```

### Daily Development Workflow

```bash
# 1. Start your services (auto-uses STG)
./run_backend.py

# 2. Run tests (auto-uses INT)
pytest

# 3. Reset your STG database if needed
USE_STG_DATABASE=true python scripts/prep_db.py

# 4. Check which database you're using
python scripts/verify_database_safety.py
```

## 📚 Database Management Scripts

### Main Tool: `prep_db.py`

The Swiss Army knife of database management:

```bash
python scripts/prep_db.py [database]  # database: int, stg, or prod
```

What it does:
1. Creates database (if local)
2. Runs migrations (reset + upgrade)
3. Seeds with test data
4. Generates embeddings
5. Calculates analytics

Examples:
```bash
python scripts/prep_db.py        # Prepares INT (default)
python scripts/prep_db.py stg    # Prepares STG
python scripts/prep_db.py prod   # Prepares PROD (requires confirmation)
```

### Safety Verification Scripts

**Check Safety System**:
```bash
python scripts/check_database_safety.py
```

**Test All Scenarios**:
```bash
python scripts/test_deployment_scenarios.py
```

**Pre-Deployment Check**:
```bash
python scripts/pre_deploy_check.py
```

**Quick Status**:
```bash
python scripts/verify_database_safety.py
```

### Other Database Scripts

**Reset Schema** (destructive!):
```bash
python scripts/reset_schema.py              # Resets INT
USE_STG_DATABASE=true python scripts/reset_schema.py  # Resets STG
```

**Seed Data**:
```bash
python scripts/reset_and_seed_yaml.py       # Seeds INT
USE_STG_DATABASE=true python scripts/reset_and_seed_yaml.py  # Seeds STG
```

## 🔧 Environment Variables

### Database Selection
- `USE_STG_DATABASE=true` - Use staging database
- `USE_PROD_DATABASE=true` - Use production database (requires confirmation)
- No flags = Use INT database (safest)

### Special Modes
- `INSTAINSTRU_PRODUCTION_MODE=true` - For production servers (skips confirmation)
- `CI=true` - For CI/CD environments (uses provided DATABASE_URL)

### Required in `.env`
```bash
# Production database
DATABASE_URL=postgresql://user:pass@supabase.com/db

# Test database
TEST_DATABASE_URL=postgresql://localhost/instainstru_test

# Staging database
STG_DATABASE_URL=postgresql://localhost/instainstru_stg

# Other required
SECRET_KEY=your-secret-key
```

## 🚨 Production Access

### Local Machine (Requires Confirmation)
```bash
USE_PROD_DATABASE=true python scripts/some_script.py
# Will show warning and ask for "yes" confirmation
```

### Production Server (Automated)
On Render/Vercel, set these environment variables:
```bash
INSTAINSTRU_PRODUCTION_MODE=true
USE_PROD_DATABASE=true
```

### CI/CD (Uses Own Database)
GitHub Actions automatically uses its test database:
```bash
CI=true
DATABASE_URL=postgresql://postgres:postgres@localhost/test
```

## 🔍 How It Works

The safety system protects at the source level:

1. **`settings.database_url` is now a property** that returns INT by default
2. **All scripts automatically safe** - old code can't bypass safety
3. **Visual indicators** - Green [INT], Yellow [STG], Red [PROD]
4. **Audit logging** - All operations logged to `logs/database_audit.jsonl`

## 🐛 Troubleshooting

### "Database configuration errors"
**Solution**: Ensure all database URLs are set in `.env`:
```bash
DATABASE_URL=...
TEST_DATABASE_URL=...
STG_DATABASE_URL=...
```

### "Production database access requested in non-interactive mode"
**Cause**: Trying to access production without a terminal
**Solutions**:
- Remove `USE_PROD_DATABASE=true`
- For servers, add `INSTAINSTRU_PRODUCTION_MODE=true`

### Wrong database being used
**Debug with**:
```bash
python scripts/verify_database_safety.py
```

### Old scripts using production
**This can't happen!** The safety system protects at the settings level.

## 📋 Best Practices

1. **Development**: Always use STG for local work
   ```bash
   ./run_backend.py  # Auto-sets USE_STG_DATABASE=true
   ```

2. **Testing**: Let tests use INT (default)
   ```bash
   pytest  # Automatically safe
   ```

3. **Migrations**: Test on INT first
   ```bash
   alembic upgrade head  # Tests on INT
   USE_STG_DATABASE=true alembic upgrade head  # Then STG
   ```

4. **Production**: Double-check everything
   ```bash
   python scripts/pre_deploy_check.py
   ```

## 🎓 Understanding the Safety Layers

1. **Environment Detection**: Automatically detects pytest, CI, local dev
2. **Flag Priority**: Explicit flags override detection
3. **Confirmation Required**: Production needs interactive "yes"
4. **Audit Trail**: All database selections logged
5. **Visual Feedback**: Color-coded database indicators

## 📊 Monitoring

Check the audit log for database access patterns:
```bash
tail -f logs/database_audit.jsonl | jq .
```

## 🚀 Deployment Checklist

Before deploying to production:

1. ✅ Run `python scripts/pre_deploy_check.py`
2. ✅ Test migrations on INT and STG
3. ✅ Set production environment variables
4. ✅ Enable `INSTAINSTRU_PRODUCTION_MODE=true` on server
5. ✅ Verify with `python scripts/test_deployment_scenarios.py`

## 📚 Related Documentation

- [Database Architecture](../architecture/database-architecture.md)
- [Migration Guide](../database/migrations.md)
- [Testing Guide](../testing/testing-guide.md)
- [Deployment Guide](../deployment/deployment-guide.md)
