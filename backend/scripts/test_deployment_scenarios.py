#!/usr/bin/env python3
"""Test database safety in different deployment scenarios."""

import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


def test_scenario(name, env_vars, expected_contains):
    """Test a specific deployment scenario."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")

    # Set environment
    original_env = {}
    for key, value in env_vars.items():
        original_env[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

    try:
        # Import fresh to get new env
        from app.core.config import settings
        from app.core.database_config import DatabaseConfig

        # Get database URL
        db_url = settings.database_url
        config = DatabaseConfig()

        print(f"Environment: {env_vars}")
        print(f"Database URL: {db_url}")
        print(f"Is CI: {config._is_ci_environment()}")
        print(f"Production Mode: {config._check_production_mode()}")

        # Check result
        if expected_contains in db_url:
            print(f"✅ PASS - Contains '{expected_contains}'")
        else:
            print(f"❌ FAIL - Expected to contain '{expected_contains}'")

    except SystemExit:
        print("❌ FAIL - System exit (probably asking for confirmation)")
    except Exception as e:
        print(f"❌ FAIL - Exception: {e}")
    finally:
        # Restore environment
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# Test scenarios
print("🧪 Testing Deployment Scenarios")

# Local development
test_scenario("Local Development (Default)", {}, "instainstru_test")

test_scenario("Local Development (STG)", {"USE_STG_DATABASE": "true"}, "instainstru_stg")

# Production server (Render)
test_scenario(
    "Production Server (Render)",
    {"INSTAINSTRU_PRODUCTION_MODE": "true", "USE_PROD_DATABASE": "true"},
    "supabase",  # or whatever your prod URL contains
)

test_scenario(
    "Production Server (Missing Flag)",
    {"INSTAINSTRU_PRODUCTION_MODE": "true"},
    "instainstru_test",  # Should default to INT
)

# CI/CD environments
test_scenario(
    "GitHub Actions",
    {"CI": "true", "GITHUB_ACTIONS": "true", "DATABASE_URL": "postgresql://github/actions"},
    "postgresql://github/actions",
)

test_scenario(
    "GitLab CI", {"CI": "true", "GITLAB_CI": "true", "DATABASE_URL": "postgresql://gitlab/ci"}, "postgresql://gitlab/ci"
)

test_scenario("CI without DATABASE_URL", {"CI": "true"}, "instainstru_test")  # Should fall back to INT

# Edge cases
test_scenario(
    "CI with Production Flags (Should Ignore)",
    {"CI": "true", "USE_PROD_DATABASE": "true", "DATABASE_URL": "postgresql://ci/test"},
    "postgresql://ci/test",  # CI takes precedence
)

test_scenario(
    "Production Mode with CI (Production Wins)",
    {"CI": "true", "INSTAINSTRU_PRODUCTION_MODE": "true", "USE_PROD_DATABASE": "true"},
    "supabase",  # Production mode overrides CI
)

print("\n✅ All deployment scenarios tested!")
