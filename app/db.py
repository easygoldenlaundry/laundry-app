# app/db.py
import os
import logging
from dotenv import load_dotenv
from fastapi import HTTPException
from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy.exc import OperationalError, DisconnectionError
from app.config import DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_POOL_TIMEOUT, DB_POOL_RECYCLE, DB_POOL_RESET_ON_RETURN, IS_PRODUCTION

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable not set.")

# Optimized engine configuration for Supabase/PostgreSQL
# This configuration helps prevent "max clients reached" errors
engine = create_engine(
    DATABASE_URL,
    # Connection pool settings optimized for Supabase Session mode
    pool_size=DB_POOL_SIZE,                    # Very conservative pool size
    max_overflow=DB_MAX_OVERFLOW,              # Limited overflow for Supabase
    pool_timeout=DB_POOL_TIMEOUT,              # Longer timeout for connection acquisition
    pool_recycle=DB_POOL_RECYCLE,              # Shorter recycle time to prevent stale connections
    pool_pre_ping=True,                        # Validate connections before use
    pool_reset_on_return=DB_POOL_RESET_ON_RETURN,  # Reset connections on return
    # Additional PostgreSQL optimizations for Supabase
    connect_args={
        "options": "-c timezone=utc -c statement_timeout=30000"  # UTC timezone + 30s statement timeout
    },
    # Echo SQL queries in development for debugging
    echo=not IS_PRODUCTION,
    # Additional settings for better connection management
    isolation_level="AUTOCOMMIT"  # Use autocommit for better connection handling
)

def get_engine():
    """Returns the global engine instance."""
    return engine

def get_session():
    """FastAPI dependency to get a DB session with retry logic."""
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            with Session(engine) as session:
                yield session
                return
        except (OperationalError, DisconnectionError) as e:
            logger.warning(f"Database connection attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delay * (attempt + 1))  # Exponential backoff
                continue
            else:
                logger.error(f"Failed to get database session after {max_retries} attempts")
                raise HTTPException(
                    status_code=503, 
                    detail="Database temporarily unavailable. Please try again."
                )
        except Exception as e:
            logger.error(f"Unexpected database error: {str(e)}")
            raise

def create_db_and_tables(max_retries=5, retry_delay=5):
    """Creates the database and all tables if they don't exist."""
    import time
    import logging
    from sqlalchemy import text, inspect

    logger = logging.getLogger(__name__)

    # Import models here to prevent circular import issues
    from . import models

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to create database tables (attempt {attempt + 1}/{max_retries})")
            SQLModel.metadata.create_all(engine)
            logger.info("Database tables created successfully")
            
            # Add missing columns for delivery cost tracking (migration)
            try:
                with engine.connect() as conn:
                    inspector = inspect(engine)
                    columns = [col['name'] for col in inspector.get_columns('order')]
                    
                    if 'delivery_cost' not in columns:
                        logger.info("Adding delivery_cost column...")
                        conn.execute(text('ALTER TABLE "order" ADD COLUMN delivery_cost FLOAT NULL'))
                        conn.commit()
                        logger.info("✅ delivery_cost column added")
                    
                    if 'delivery_distance_km' not in columns:
                        logger.info("Adding delivery_distance_km column...")
                        conn.execute(text('ALTER TABLE "order" ADD COLUMN delivery_distance_km FLOAT NULL'))
                        conn.commit()
                        logger.info("✅ delivery_distance_km column added")
            except Exception as e:
                logger.warning(f"Column migration check failed (may already exist): {e}")
            
            # Log initial pool status
            pool = engine.pool
            logger.info(f"Database pool initialized: size={pool.size()}, max_overflow={engine.pool._max_overflow}")
            return
        except Exception as e:
            logger.warning(f"Database connection attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                # Increase delay for next attempt
                retry_delay = min(retry_delay * 2, 30)  # Exponential backoff, max 30s
            else:
                logger.error(f"Failed to create database tables after {max_retries} attempts: {str(e)}")
                # Don't raise the exception - allow the app to start without tables
                # Tables will be created on first successful connection
                logger.warning("Continuing without creating tables - they will be created on first successful database connection")

def cleanup_connections():
    """Clean up database connections and reset the pool."""
    try:
        logger.info("Cleaning up database connections...")
        engine.dispose()
        logger.info("Database connections cleaned up successfully")
    except Exception as e:
        logger.error(f"Failed to cleanup database connections: {str(e)}")

def get_pool_status():
    """Get current connection pool status for monitoring."""
    try:
        pool = engine.pool
        return {
            "size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "total": pool.checkedin() + pool.checkedout()
        }
    except Exception as e:
        logger.error(f"Failed to get pool status: {str(e)}")
        return {"error": str(e)}