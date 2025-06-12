# InstaInstru Development Scripts

This directory contains utility scripts to help with development, debugging, and onboarding.

## project_overview.py
Generates a comprehensive overview of the project for new developers, including database structure, codebase organization, feature status, and quick start guide.

```bash
python scripts/project_overview.py
```

**Use this when:**
- Onboarding new team members
- Getting a quick snapshot of the project state
- Understanding the database schema and relationships
- Checking feature implementation status

## reset_and_seed_database.py
Resets the database and populates it with test data while preserving specified user accounts.

```bash
python scripts/reset_and_seed_database.py
```

**Features:**
- Cleans up test data while preserving important accounts
- Creates 10 diverse test instructors with realistic profiles
- Generates availability patterns for testing
- All test accounts use password: `TestPassword123!`

**Use this when:**
- Starting fresh development
- Testing new features
- Demonstrating the platform

## find_text_occurrences.py
Searches the entire codebase for specific text patterns (case-insensitive).

```bash
python scripts/find_text_occurrences.py
```

**Use this when:**
- Refactoring or renaming across the codebase
- Finding all usages of a specific term
- Ensuring complete updates during rebranding

## check_column_type.py
Utility script to verify database column types.

```bash
python scripts/check_column_type.py
```

**Use this when:**
- Debugging type mismatches between database and models
- Verifying migration results
- Troubleshooting validation errors

## Usage Notes

1. All scripts should be run from the backend directory:
   ```bash
   cd backend
   python scripts/<script_name>.py
   ```

2. Make sure your virtual environment is activated:
   ```bash
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Ensure your `.env` file is properly configured with database credentials.

## Adding New Scripts

When adding new utility scripts:
1. Include a clear docstring at the top explaining the purpose
2. Add error handling for common issues
3. Update this README with usage instructions
4. Follow the existing naming convention (lowercase with underscores)