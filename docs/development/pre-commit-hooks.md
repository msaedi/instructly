# Pre-commit Hooks & Defensive Architecture

*Last Updated: Session v88 - Architectural Defense System Active*

## Overview

InstaInstru uses a comprehensive pre-commit hook system to prevent regression of critical architectural achievements. These automated defenses ensure that hard-won improvements in repository pattern (29% → TRUE 100%) and timezone consistency (28 fixes) are permanently protected.

## Why Defensive Measures Matter

### The Achievement at Risk
- **Repository Pattern**: Took sessions v86-v88 to fix 107 violations from 29% to TRUE 100%
- **Timezone Consistency**: Fixed 28 global timezone issues affecting user experience
- **Investment Protection**: Hundreds of hours of architectural work must not regress
- **Quality Assurance**: Zero-tolerance policy for architectural violations

### Multi-Layer Defense Strategy
1. **Local Development**: Pre-commit hooks block violations before commit
2. **Git Level**: Commits are rejected if hooks are bypassed
3. **Pull Request Level**: GitHub Actions runs all checks on PRs
4. **Merge Protection**: PRs cannot merge if violations are detected

## Active Defensive Hooks

### 1. Repository Pattern Compliance (`check-repository-pattern`)

**Purpose**: Ensures services only use repositories for database access, maintaining clean architecture.

#### What It Protects
- Prevents regression from TRUE 100% repository pattern compliance
- Blocks direct `db.query()` calls in service layer
- Maintains clean separation between business logic and data access
- Protects architectural investment of 107 violations fixed

#### Violation Patterns Detected
```python
# ❌ These will be BLOCKED by pre-commit:
self.db.query(User).filter(...)
self.db.add(booking)
self.db.commit()
session.query(Model).all()

# ✅ Use repositories instead:
self.repository.get_user_by_id(user_id)
self.repository.create_booking(booking_data)
```

#### Bypass Markers (Temporary Only)
```python
# For legitimate database access (like BaseService transactions):
# repo-pattern-ignore: Transaction management requires direct DB
with self.db.begin_nested():
    ...

# For code scheduled for migration:
# repo-pattern-migrate: TODO: Create UserRepository
user = self.db.query(User).filter_by(id=user_id).first()
```

#### Files Checked
- `backend/app/services/*.py`
- `backend/app/core/*.py`
- Excludes: test files, repository files themselves

### 2. Timezone Consistency (`check-timezone-usage`)

**Purpose**: Prevents timezone bugs by blocking `date.today()` in user-facing code.

#### What It Protects
- Prevents reintroduction of 28 fixed timezone bugs
- Ensures all user-facing dates are timezone-aware
- Maintains global compatibility for NYC-based marketplace

#### Violation Patterns Detected
```python
# ❌ This will be BLOCKED in user-facing code:
today = date.today()
if booking_date < today:
    raise Error("Cannot book past date")

# ✅ Use timezone-aware alternative:
from app.core.timezone_utils import get_user_today_by_id
user_today = get_user_today_by_id(user_id, self.db)
if booking_date < user_today:
    raise Error("Cannot book past date")
```

#### Allowed Exceptions
- Test files (`test_*.py`)
- System services (`cache_service.py`, `logging_service.py`, `metrics_service.py`)
- System-level operations that genuinely need server time

#### Files Checked
- `backend/app/routes/*.py`
- `backend/app/services/*.py`
- `backend/app/api/*.py`

### 3. API Contract Compliance (`api-contracts`)

**Purpose**: Ensures all API endpoints return proper Pydantic response models.

#### What It Protects
- Prevents API contract regressions
- Ensures type safety across entire API surface
- Maintains consistent response formats
- Protects against raw dict/list returns

#### Requirements Enforced
- All routes must use `response_model=` parameter
- Response models must be proper Pydantic classes
- No raw dict or list returns from endpoints

#### Files Checked
- `backend/app/routes/*.py`

## Standard Code Quality Hooks

### Formatting & Style
- **black**: Code formatting (120 char line length)
- **isort**: Import sorting with consistent patterns
- **trailing-whitespace**: Remove trailing spaces
- **end-of-file-fixer**: Ensure files end with newline

### Configuration Validation
- **check-yaml**: Validate YAML syntax
- **check-added-large-files**: Prevent large file commits (>500KB)
- **check-merge-conflict**: Detect unresolved merge conflicts

## Hook Configuration

### Installation
Pre-commit hooks are already configured. To ensure they're active:
```bash
cd /Users/mehdisaedi/instructly
pre-commit install
```

### Configuration File: `.pre-commit-config.yaml`
```yaml
repos:
  # Custom Architectural Defense Hooks
  - repo: local
    hooks:
    - id: check-repository-pattern
      name: Repository Pattern Compliance
      entry: python backend/scripts/check_repository_pattern.py
      language: system
      files: ^backend/app/(services|core)/.*\.py$

    - id: check-timezone-usage
      name: Timezone Consistency Check
      entry: python backend/scripts/check_timezone_usage.py backend/app/
      language: system
      files: ^backend/app/(routes|services|api)/.*\.py$

    - id: api-contracts
      name: API Contract Compliance
      entry: backend/scripts/check_api_contracts_wrapper.sh
      language: system
      files: ^backend/app/routes/.*\.py$

  # Standard Code Quality Hooks
  - repo: https://github.com/psf/black
    rev: 23.12.1
    hooks:
    - id: black
      args: [--line-length=120]

  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
    - id: isort
      args: [--profile=black, --line-length=120]
```

## Manual Hook Execution

### Run Individual Hooks
```bash
# Check repository pattern compliance
python backend/scripts/check_repository_pattern.py

# Check timezone usage
python backend/scripts/check_timezone_usage.py backend/app/

# Check API contracts
backend/scripts/check_api_contracts_wrapper.sh

# Run all pre-commit hooks
pre-commit run --all-files
```

### Run on Specific Files
```bash
# Check specific service
python backend/scripts/check_repository_pattern.py backend/app/services/booking_service.py

# Run hooks on staged files only
pre-commit run
```

## CI/CD Integration

### GitHub Actions Workflow
```yaml
name: Pre-commit Checks
on: [push, pull_request]

jobs:
  pre-commit:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    - uses: pre-commit/action@v3.0.0
```

### Merge Protection Rules
GitHub branch protection enforces:
1. All status checks must pass
2. Pre-commit hooks must succeed
3. No bypassing merge requirements
4. Up-to-date branch requirement

## Emergency Bypassing (USE SPARINGLY)

### Bypass All Hooks (Emergency Only)
```bash
git commit --no-verify -m "Emergency fix: [reason]"
```

**⚠️ WARNING**: Only use for critical production fixes. Create follow-up task to fix violations.

### Bypass Individual Hooks
```bash
# Skip specific hook
SKIP=check-repository-pattern git commit -m "Fix with planned follow-up"
```

## Hook Performance

### Execution Times
- Repository pattern check: ~2-3 seconds
- Timezone check: ~1-2 seconds
- API contract check: ~3-4 seconds
- Black formatting: ~1-2 seconds
- Total pre-commit time: ~8-12 seconds

### Optimization Features
- Only checks modified files (not entire codebase)
- Concurrent execution where possible
- Cached results for unchanged files
- Fast fail on first violation

## Monitoring & Metrics

### Success Indicators
- Zero repository pattern violations since v88
- Zero timezone consistency regressions
- 100% API contract compliance maintained
- No architectural debt accumulation

### Failure Patterns
Monitor logs for:
- Attempted repository pattern violations
- Timezone usage in user-facing code
- API endpoints without response models
- Developers bypassing hooks frequently

## Educational Resources

### For New Developers
1. **Repository Pattern Guide**: `docs/architecture/06_repository_pattern_architecture.md`
2. **Timezone Best Practices**: `docs/architecture/timezone-handling.md`
3. **API Standards**: `docs/api/api-standards-guide.md`

### Common Violations & Fixes
#### Repository Pattern
```python
# Instead of:
user = db.query(User).filter(User.id == user_id).first()

# Use:
user = self.user_repository.get_by_id(user_id)
```

#### Timezone Handling
```python
# Instead of:
today = date.today()

# Use:
today = get_user_today_by_timezone(user.timezone)
```

#### API Contracts
```python
# Instead of:
@router.get("/users")
def get_users():
    return {"users": [...]}

# Use:
@router.get("/users", response_model=UsersResponse)
def get_users():
    return UsersResponse(users=[...])
```

## Maintenance

### Adding New Hooks
1. Create check script in `backend/scripts/`
2. Add hook to `.pre-commit-config.yaml`
3. Test with `pre-commit run --all-files`
4. Update CI/CD workflows
5. Document in this file

### Updating Hook Configuration
1. Modify `.pre-commit-config.yaml`
2. Run `pre-commit install` to update
3. Test on sample violations
4. Communicate changes to team

## Architecture Philosophy

### Defense in Depth
These hooks implement "defense in depth" - multiple layers of protection:
1. **Developer Education**: Clear documentation and examples
2. **Local Prevention**: Pre-commit hooks catch violations early
3. **CI/CD Enforcement**: GitHub Actions prevent bad merges
4. **Merge Protection**: Branch protection rules as final gate

### Zero Tolerance Policy
- **No Architectural Debt**: Violations are blocked, not accumulated
- **No Regression**: Hard-won improvements are permanently protected
- **Quality Gate**: Only clean code enters the main branch

### Investment Protection
These hooks protect hundreds of hours of architectural work:
- Repository pattern migration: 107 violations fixed
- Timezone consistency: 28 global issues resolved
- API standardization: 32 endpoints with Pydantic models
- **Result**: World-class backend architecture maintained permanently

---

**The defensive measures are permanent and non-negotiable - they protect the architectural achievements that earned our megawatts! ⚡**
