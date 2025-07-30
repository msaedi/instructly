# Database Safety System

## Overview

The InstaInstru platform implements a three-tier database safety system to prevent accidental modifications to production data. This system provides clear separation between test, development, and production databases with visual indicators and safety checks.

## Three-Tier Database Architecture

### 1. INT (Integration Test Database) - 🟢 Default
- **Purpose**: Used exclusively for pytest and automated testing
- **Access**: Default - no flags required
- **Safety**: Can be freely dropped and rebuilt
- **Visual Indicator**: Green `[INT]` in scripts
- **Example URL**: `postgresql://user:pass@localhost:5432/instainstru_int`

### 2. STG (Staging/Local Development Database) - 🟡 Caution
- **Purpose**: Local development with persistent data
- **Access**: Requires `USE_STG_DATABASE=true`
- **Safety**: Preserves data between test runs
- **Visual Indicator**: Yellow `[STG]` in scripts
- **Example URL**: `postgresql://user:pass@localhost:5432/instainstru_stg`

### 3. PROD (Production Database) - 🔴 Danger
- **Purpose**: Real production data
- **Access**: Requires `USE_PROD_DATABASE=true` + interactive confirmation
- **Safety**: Multiple confirmation steps required
- **Visual Indicator**: Red `[PROD]` in scripts
- **Example URL**: Supabase or other cloud provider

## Current Features

### ✅ Implemented Safety Features

1. **Three-Tier Architecture**: Complete separation of test, staging, and production databases
2. **Production Confirmation**: Interactive "yes" confirmation required for production access
3. **Test Isolation**: Tests are forced to use INT database, ignoring environment flags
4. **Environment Detection**: Automatic detection of pytest, local dev, and production environments
5. **Audit Logging**: All database operations logged to `logs/database_audit.jsonl`
6. **Visual Indicators**: Color-coded database selection in scripts
7. **Configuration Validation**: Startup checks ensure all databases are properly configured
8. **Masked URLs**: Database URLs are masked in logs to prevent credential exposure
9. **Interactive Check**: Non-interactive mode blocks production access
10. **Database Safety Score**: Metrics tracking safety feature implementation

### 🔄 Future Features (Extension Points)

- Automated backups before destructive operations
- Schema version validation
- Dry-run mode for dangerous operations
- Rate limiting for production access
- Role-based database access control
- Encryption at rest verification
- Point-in-time recovery integration

## Usage Examples

### Running Tests (INT Database)
```bash
# Default - uses INT database automatically
pytest

# Even with production flag, tests still use INT
USE_PROD_DATABASE=true pytest  # Still uses INT!
```

### Local Development (STG Database)
```bash
# Start development server with staging database
USE_STG_DATABASE=true uvicorn app.main:app --reload

# Reset staging database
./backend/scripts/manage_db.sh --reset stg
```

### Production Operations (PROD Database)
```bash
# Requires confirmation
USE_PROD_DATABASE=true python scripts/some_script.py
# Will prompt: "Type 'yes' to confirm production access:"

# Production reset (extremely dangerous!)
./backend/scripts/manage_db.sh --reset prod
```

## Common Workflows

### Setting Up Local Development

1. Create your databases:
```sql
CREATE DATABASE instainstru_int;     -- For tests
CREATE DATABASE instainstru_stg;     -- For development
```

2. Configure your `.env` file:
```env
# Integration test database
test_database_url=postgresql://user:pass@localhost:5432/instainstru_int

# Staging/local development database
stg_database_url=postgresql://user:pass@localhost:5432/instainstru_stg

# Production database (be careful!)
database_url=postgresql://user:pass@supabase.com:5432/instainstru_prod
```

3. Initialize your staging database:
```bash
./backend/scripts/manage_db.sh --reset stg
```

### Running Tests Safely

```bash
# All of these use INT database:
pytest
pytest tests/test_auth.py
pytest -k "test_login"
```

### Database Management Script

The `manage_db.sh` script provides safe database operations:

```bash
# Reset integration test database (safe)
./backend/scripts/manage_db.sh --reset int

# Seed staging database (preserves existing data)
./backend/scripts/manage_db.sh --seed stg

# Production operations require extra confirmation
./backend/scripts/manage_db.sh --reset prod  # DANGER!
```

## Recovery Procedures

### If You Accidentally Modified Production Data

1. **STOP** all operations immediately
2. Check the audit log: `tail -f backend/logs/database_audit.jsonl`
3. Contact the team lead or database administrator
4. Document what was changed in the incident report
5. If possible, use database backups to restore

### If You Deleted Staging Data

1. Simply re-run the reset command:
   ```bash
   ./backend/scripts/manage_db.sh --reset stg
   ```

2. Your development data will be restored from seed files

### Emergency Contacts

- **Database Administrator**: [Contact Info]
- **Team Lead**: [Contact Info]
- **24/7 Support**: [Contact Info]

## Database Safety Score

The system tracks safety implementation with a score (currently 56.3%):

```json
{
  "score": 56.3,
  "implemented_features": 9,
  "total_features": 16,
  "metrics": {
    "three_tier_architecture": true,
    "production_confirmation": true,
    "test_isolation": true,
    "environment_detection": true,
    "audit_logging": true,
    "visual_indicators": true,
    "configuration_validation": true,
    "masked_urls": true,
    "interactive_check": true,
    "automated_backups": false,
    "schema_validation": false,
    "dry_run_mode": false,
    "rate_limiting": false,
    "role_based_access": false,
    "encryption_at_rest": false,
    "point_in_time_recovery": false
  }
}
```

## CI/CD Configuration

### GitHub Actions / CI

Ensure your CI environment uses the INT database:

```yaml
env:
  test_database_url: ${{ secrets.TEST_DATABASE_URL }}
  # Do NOT set USE_STG_DATABASE or USE_PROD_DATABASE
```

### Deployment Scripts

Production deployments should explicitly set:
```bash
export USE_PROD_DATABASE=true
# But ensure migrations are tested on staging first!
```

## Migration from Old System

If you're still using `USE_TEST_DATABASE`:

1. The system will show a deprecation warning
2. `USE_TEST_DATABASE=true` now maps to default INT behavior
3. Update your scripts to use the new flags:
   - Remove `USE_TEST_DATABASE=true`
   - Add `USE_STG_DATABASE=true` for local development

## Troubleshooting

### "INT database URL not configured"
- Set `test_database_url` in your `.env` file
- This should point to your integration test database

### "STG database URL not configured"
- Set `stg_database_url` in your `.env` file
- This should point to your local development database

### "Production access requested in non-interactive mode"
- Production access requires an interactive terminal
- This prevents accidental production access in scripts
- Use staging database for automated scripts

### Tests failing with database errors
- Ensure `test_database_url` points to a valid test database
- The database name should contain "test" or "int"
- Run: `./backend/scripts/manage_db.sh --reset int`

## Best Practices

1. **Always use STG for local development** - preserves your test data
2. **Never store production credentials in `.env`** - use environment variables
3. **Review audit logs regularly** - `tail -f logs/database_audit.jsonl`
4. **Test migrations on INT first**, then STG, then PROD
5. **Use the management script** instead of manual database commands
6. **Check the safety score** to ensure all features are working

## Architecture Decisions

This system was designed with several principles:

1. **Safety by Default**: INT database is the default to prevent accidents
2. **Progressive Disclosure**: More dangerous operations require more steps
3. **Visual Clarity**: Color coding makes database selection obvious
4. **Audit Everything**: Start collecting data now for future analysis
5. **Extension Points**: Empty methods ready for enterprise features
6. **No Wasted Work**: Every line of code stays as we add features

The skeleton architecture allows us to solve immediate safety issues (2-4 hours of work) while building the foundation for enterprise-grade database management features.
