# backend/scripts/reset_schema.py
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text

from app.core.config import settings

# Use test database if USE_TEST_DATABASE is set
db_url = settings.test_database_url if os.getenv("USE_TEST_DATABASE") == "true" else settings.database_url
print(f"Using database: {'TEST' if os.getenv('USE_TEST_DATABASE') == 'true' else 'PRODUCTION'}")

engine = create_engine(db_url)
with engine.connect() as conn:
    conn.execute(text("DROP SCHEMA public CASCADE"))
    conn.execute(text("CREATE SCHEMA public"))
    conn.commit()
print("Schema reset complete!")
