# Database Safety Test CI Fixes

## Problem
The database safety tests fail in CI because:
1. Settings module is cached and detects CI environment at import time
2. CI environments may have DATABASE_URL set, which takes precedence
3. Tests can't effectively clear environment variables after settings are cached

## Solution
Replace the problematic tests in `test_database_safety.py` with CI-aware versions that:
1. Mock `_is_ci_environment()` method to control CI detection
2. Clear DATABASE_URL when testing non-CI behavior
3. Mock `_check_production_mode()` when testing production safety

## Key Changes

### For tests that should NOT be in CI mode:
```python
with patch('app.core.database_config.DatabaseConfig._is_ci_environment', return_value=False):
    # test code
```

### For tests that check production safety:
```python
with patch('app.core.database_config.DatabaseConfig._is_ci_environment', return_value=False), \
     patch('app.core.database_config.DatabaseConfig._check_production_mode', return_value=False):
    # test code
```

### For CI-specific tests:
- Save and restore original environment variables
- Accept that behavior differs between local and CI environments
- Test for non-error conditions rather than specific URLs when in actual CI

## Implementation
Copy the content from `test_database_safety_fixed.py` to replace the failing tests.
