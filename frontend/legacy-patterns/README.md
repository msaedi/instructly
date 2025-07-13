# Legacy Patterns - Technical Debt Isolation

This directory contains files that represent the old mental model of the application, isolated as part of the Phoenix Frontend Initiative (Week 1).

## Background

These files were moved here to isolate technical debt while keeping the instructor dashboard functional. They represent a flawed mental model where:

- **Slots are treated as database entities with IDs** (WRONG - they're just time blocks)
- **Complex operation patterns** for what should be simple time-based queries
- **Overly complex helper functions** for basic time slot operations

## Files in this directory:

### 1. `useAvailabilityOperations.ts` (600+ lines → should be ~50)
- Contains the operation pattern that's 12x larger than needed
- Treats slots as entities when they're just instructor_id + date + time ranges
- Will be replaced with clean time-based booking logic

### 2. `operationGenerator.ts` (DELETE ENTIRELY)
- Generates complex operations for what should be simple API calls
- Part of the wrong mental model about slots having IDs
- No longer needed in the clean architecture

### 3. `slotHelpers.ts` (complex → simple)
- Contains overly complex logic for time slot manipulation
- Should be simple time helpers without slot ID references
- Will be replaced with straightforward time utilities

## Migration Plan

As part of the Phoenix Frontend Initiative:
- **Week 1**: Isolate these files (DONE)
- **Week 2**: Build new clean components for students
- **Week 3**: Create adapter layer for instructor dashboard
- **Week 4**: Migrate instructor dashboard to new patterns
- **Week 5+**: Delete this directory entirely

## Important Note

**DO NOT** add new imports to these files. They are scheduled for deletion. Any new features should use the clean patterns in the `features/` directory.
