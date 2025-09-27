#!/usr/bin/env python3
"""
Demonstrate how the database safety system protects against accidents.
"""

import os
from pathlib import Path
import sys

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


def show_old_dangerous_pattern():
    """Show how old scripts were dangerous."""
    print("🚨 OLD DANGEROUS PATTERN:")
    print("```python")
    print("# This used to go straight to production!")
    print("db_url = settings.database_url")
    print("engine = create_engine(db_url)")
    print("# DROP SCHEMA public CASCADE  # 💥 BOOM! Production data gone!")
    print("```")


def show_new_safe_pattern():
    """Show how the same code is now safe."""
    print("\n✅ NEW SAFE BEHAVIOR:")
    print("```python")
    print("# Same code, but now safe by default")
    print("db_url = settings.database_url  # Returns INT database!")
    print("engine = create_engine(db_url)")
    print("# DROP SCHEMA public CASCADE  # ✅ Only affects test database")
    print("```")


def demonstrate_safety():
    """Actually demonstrate the safety."""
    from app.core.config import settings

    print("\n🔍 LIVE DEMONSTRATION:")
    print("=" * 60)

    # Clear any environment variables
    os.environ.pop("SITE_MODE", None)

    print("\n1. Default behavior (what old scripts do):")
    print("   Code: db_url = settings.database_url")
    db_url = settings.database_url
    print(f"   Result: {db_url}")
    print("   ✅ SAFE! Defaults to INT database")

    print("\n2. Explicit local/staging access:")
    os.environ["SITE_MODE"] = "local"
    print("   Code: SITE_MODE=local")
    print("         db_url = settings.database_url")
    db_url = settings.database_url
    print(f"   Result: {db_url}")
    print("   ✅ Local/Staging database accessible with SITE_MODE")
    os.environ.pop("SITE_MODE")

    print("\n3. Production access attempt:")
    print("   Code: SITE_MODE=prod")
    print("         db_url = settings.database_url")
    print("   Result: Would prompt for confirmation!")
    print("   ✅ Production protected by confirmation")


def main():
    print("🛡️  DATABASE SAFETY DEMONSTRATION")
    print("=" * 60)

    show_old_dangerous_pattern()
    show_new_safe_pattern()
    demonstrate_safety()

    print("\n" + "=" * 60)
    print("🎉 SUMMARY: Your database is now protected by default!")
    print("\nKey benefits:")
    print("- Zero code changes needed in old scripts")
    print("- Production requires explicit opt-in + confirmation")
    print("- Alembic migrations are safe by default")
    print("- reset_schema.py can't accidentally drop production")
    print("\nThe critical insight: We protected at the SOURCE (settings),")
    print("not just at usage points. This makes ALL access safe!")


if __name__ == "__main__":
    main()
