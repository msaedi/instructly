# backend/app/database.py
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
from .core.config import settings
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Create engine with connection pooling
engine = create_engine(
    settings.database_url,
    # Connection pool settings
    poolclass=QueuePool,
    pool_size=20,           # Number of persistent connections
    max_overflow=10,        # Maximum overflow connections
    pool_timeout=30,        # Timeout for getting connection
    pool_recycle=3600,      # Recycle connections after 1 hour
    pool_pre_ping=True,     # Test connections before using
    echo_pool=False,        # Set to True for pool debugging
    connect_args={
        "connect_timeout": 10,
        "application_name": "instainstru_backend"
    }
)

# Log pool events for monitoring
@event.listens_for(engine, "connect")
def receive_connect(dbapi_connection, connection_record):
    connection_record.info['connect_time'] = datetime.now()
    logger.debug("Database connection established")

@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    logger.debug(f"Connection checked out from pool")

@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_connection, connection_record):
    logger.debug(f"Connection returned to pool")

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)

Base = declarative_base()

def get_db():
    """Get database session with proper cleanup."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except:
        db.rollback()
        raise
    finally:
        db.close()

def get_db_pool_status():
    """Get current database pool statistics."""
    pool = engine.pool
    return {
        "size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "total": pool.size() + pool.overflow(),
        "overflow": pool.overflow()
    }