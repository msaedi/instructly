# Repository Pattern Migration Status

## Overview
This document tracks the migration from direct database queries to the repository pattern across the InstaInstru backend.

**Last Updated**: December 2024

## Current Status
- **Repository Pattern Coverage**: 29% (7/24 services)
- **Total Violations Found**: 98
- **Violations Marked for Migration**: 3
- **Violations Fixed**: 0
- **Target Coverage**: 100%

## Pre-commit Hook
Repository pattern compliance is enforced by a pre-commit hook. Services with violations must be marked with migration comments to allow commits during the transition period.

## Migration Progress

### ✅ Compliant Services (No violations)
These services properly use the repository pattern:
- [x] BookingService
- [x] AvailabilityService
- [x] InstructorService
- [x] SlotManager
- [x] BulkOperationService
- [x] WeekOperationService
- [x] AuthService (1 db.refresh marked)

### 🔄 In Migration
Services with violations marked for migration:

#### ConflictChecker (2 violations)
- **Status**: Has repository but doesn't use it
- **Priority**: HIGH - Easy fix
- **Violations**: Lines 268, 358 (User queries)
- **Fix**: Use existing ConflictCheckerRepository

#### PermissionService (25 violations)
- **Status**: No repository
- **Priority**: HIGH - Security critical
- **Needs**: UserRepository, RBACRepository
- **Models**: User, Permission, Role, UserPermission

#### PrivacyService (32 violations)
- **Status**: No repository
- **Priority**: HIGH - GDPR compliance
- **Needs**: UserRepository, multiple repositories
- **Models**: User, SearchHistory, SearchEvent, Booking, InstructorProfile

#### SearchHistoryService (13 violations)
- **Status**: Has repository but mixed usage
- **Priority**: MEDIUM
- **Fix**: Migrate to existing SearchHistoryRepository

#### SearchHistoryCleanupService (19 violations)
- **Status**: No repository
- **Priority**: MEDIUM - Batch operations
- **Needs**: SearchHistoryRepository extensions

#### NotificationService (1 violation)
- **Status**: No repository
- **Priority**: LOW
- **Fix**: Use BookingRepository

#### Other Services with Minor Violations
- PasswordResetService (1 violation - db.flush)
- InstructorService (1 violation - db.flush)
- BulkOperationService (1 violation - db.rollback)
- SlotManager (1 violation - db.refresh)

### ❌ Utilities with Violations
- timezone_utils (1 violation) - Should pass User object instead of querying

## Missing Repositories

### Critical (Needed immediately)
1. **UserRepository** - Used by multiple services
2. **RBACRepository** - For Permission, Role, UserPermission models

### Nice to Have
3. **PasswordResetRepository**
4. **MonitoringRepository**

## Migration Guide

### Step 1: Mark Existing Violations
```bash
# Generate list of violations
cd backend
python scripts/check_repository_pattern.py --generate-markers

# Manually add markers or use helper script
python scripts/mark_repository_violations.py
```

### Step 2: Fix Violations Incrementally

#### For services WITH repositories:
```python
# Before (violation)
user = self.db.query(User).filter(User.id == user_id).first()

# After (using repository)
user = self.repository.get_by_id(user_id)
```

#### For services WITHOUT repositories:
1. Create the repository
2. Inject it into the service
3. Replace direct queries with repository calls

### Step 3: Remove Migration Markers
As you fix each violation, remove the `# repo-pattern-migrate` comment.

### Step 4: Verify Compliance
```bash
python scripts/check_repository_pattern.py
```

## How to Add Migration Markers

### Temporary Migration (will be fixed)
```python
# repo-pattern-migrate: TODO: Use UserRepository when created
user = self.db.query(User).filter(User.id == user_id).first()
```

### Permanent Legitimate Use
```python
# repo-pattern-ignore: Transaction management requires direct DB access
self.db.commit()
```

## Enforcement

### Pre-commit Hook
The `.pre-commit-config.yaml` includes:
```yaml
- id: check-repository-pattern
  name: Check Repository Pattern Compliance
  entry: python backend/scripts/check_repository_pattern.py
  language: system
  files: ^backend/app/(services|core)/.*\.py$
```

### CI/CD Pipeline
GitHub Actions will fail PRs with unmarked violations.

## Success Metrics

### Phase 1 Goals (Current)
- [x] Create violation detection script
- [x] Add pre-commit hook
- [x] Mark existing violations
- [ ] Create UserRepository
- [ ] Create RBACRepository

### Phase 2 Goals
- [ ] Fix ConflictChecker (use existing repository)
- [ ] Migrate PermissionService
- [ ] Migrate SearchHistoryService

### Phase 3 Goals
- [ ] Migrate PrivacyService
- [ ] Migrate SearchHistoryCleanupService
- [ ] Fix all minor violations

### Phase 4 Goals
- [ ] Remove all migration markers
- [ ] Achieve 100% repository pattern compliance
- [ ] Update documentation

## Benefits of Completion

1. **Better Testing**: Mock repositories instead of database
2. **Cleaner Architecture**: Proper separation of concerns
3. **Easier Maintenance**: Database logic in one place
4. **Performance**: Easier to add caching
5. **Type Safety**: Repository interfaces provide contracts

## Notes

- Services in `base.py` may legitimately need direct DB access for transactions
- Test files are excluded from checks
- Repository files themselves are allowed DB access
- The tracking file `.repository-migration-tracking.json` tracks progress
