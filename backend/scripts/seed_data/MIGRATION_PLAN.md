# Seed Data Migration Plan

## Overview
This document outlines the migration from the hardcoded seed data system to the new YAML-based configuration system.

## Migration Benefits

1. **Maintainability**: YAML files are easier to read and modify than Python code
2. **Duration Options**: Full support for the new `duration_options` array field
3. **Modularity**: Separate files for different data types (instructors, students, patterns)
4. **Consistency**: Reusable availability patterns across instructors
5. **Safety**: Only affects @example.com test accounts

## Migration Steps

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt  # PyYAML==6.0.1 has been added
```

### Step 2: Review YAML Configuration
- `config.yaml` - Default settings and passwords
- `instructors.yaml` - 14 instructors with diverse duration_options
- `students.yaml` - 5 test student accounts
- `availability_patterns.yaml` - 5 reusable schedule patterns
- `bookings.yaml` - Placeholder for future booking scenarios

### Step 3: Run New Seed Script
```bash
# For production database (default)
python scripts/reset_and_seed_yaml.py

# For test database
USE_TEST_DATABASE=true python scripts/reset_and_seed_yaml.py
```

### Step 4: Verify Data
The script will create:
- 5 students
- 14 instructors
- 20 services (with varied duration_options)
- ~28 bookings using different durations
- 4 weeks of availability

### Step 5: Deprecate Old Scripts
After verification, the following can be archived:
- `reset_and_seed_database_enhanced.py` (old hardcoded version)
- Any instructor/student template constants

## Key Differences

### Old System (Hardcoded)
- Duration stored as single `duration_override` integer
- Instructor data embedded in Python code
- Difficult to modify without code changes
- Limited variety in test data

### New System (YAML-based)
- Duration stored as `duration_options` array (e.g., [30, 60, 90])
- Configuration in readable YAML files
- Easy to add/modify instructors and services
- Rich variety showcasing all platform features

## Duration Options Examples

The new system showcases various duration configurations:
- Single duration: `[60]` (traditional 1-hour sessions)
- Two options: `[45, 60]` (flexibility for shorter/longer)
- Three options: `[30, 60, 90]` (maximum flexibility)
- Extended sessions: `[90, 120]` (test prep, workshops)

## Rollback Plan

If issues occur:
1. The old script `reset_and_seed_database_enhanced.py` remains available
2. YAML seed only affects @example.com accounts
3. Production data is never touched

## Verification Queries

```sql
-- Check duration variety
SELECT array_length(duration_options, 1) as options, count(*)
FROM services GROUP BY 1 ORDER BY 1;

-- Verify bookings use various durations
SELECT duration_minutes, count(*)
FROM bookings GROUP BY 1 ORDER BY 1;
```

## Next Steps

1. Update any documentation referencing the old seed system
2. Train team on modifying YAML files for test data
3. Consider extending YAML system for other test scenarios
