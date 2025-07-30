# backend/scripts/reset_schema.py
"""
Reset database schema - DROPS ALL TABLES!

Database safety: This script now uses safe database selection
Default: INT database
Use USE_STG_DATABASE=true or USE_PROD_DATABASE=true for other databases
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

from app.core.config import settings

# Use the safe database URL property
db_url = settings.database_url

print("\n" + "=" * 60)
print("⚠️  SCHEMA RESET - This will DROP ALL TABLES!")
print("=" * 60)

engine = create_engine(db_url)
with engine.connect() as conn:
    conn.execute(text("DROP SCHEMA public CASCADE"))
    conn.execute(text("CREATE SCHEMA public"))
    conn.commit()
print("Schema reset complete!")
