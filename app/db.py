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
    # CRITICAL FIX: Use READ COMMITTED isolation for proper transactions
    # AUTOCOMMIT causes race conditions with concurrent station updates!
    isolation_level="READ COMMITTED"
)

def get_engine():
    """Returns the global engine instance."""
    return engine

def get_session():
    """
    FastAPI dependency to get a DB session with retry logic and automatic recovery.
    Handles connection failures, dead connections, and pool exhaustion gracefully.
    """
    max_retries = 3
    retry_delay = 0.5
    
    for attempt in range(max_retries):
        try:
            with Session(engine) as session:
                # Test the connection before yielding
                try:
                    session.execute("SELECT 1")
                except Exception as test_error:
                    logger.warning(f"Connection test failed: {test_error}, disposing pool")
                    engine.dispose()  # Reset pool if connections are stale
                    raise
                
                yield session
                return
        except (OperationalError, DisconnectionError) as e:
            error_msg = str(e).lower()
            logger.warning(f"Database connection attempt {attempt + 1} failed: {str(e)}")
            
            # Reset pool on connection errors
            if attempt == 0:  # Only dispose on first error to avoid excessive resets
                logger.info("Disposing connection pool due to connection error")
                engine.dispose()
            
            if attempt < max_retries - 1:
                import time
                backoff = retry_delay * (2 ** attempt)  # Exponential backoff
                logger.info(f"Retrying in {backoff}s...")
                time.sleep(backoff)
                continue
            else:
                logger.error(f"Failed to get database session after {max_retries} attempts")
                # Log pool status for debugging
                try:
                    pool_status = get_pool_status()
                    logger.error(f"Final pool status: {pool_status}")
                except:
                    pass
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

async def monitor_connection_pool():
    """
    Background task that monitors connection pool health and performs maintenance.
    Prevents connection buildup and detects/fixes stale connections.
    """
    import asyncio
    from app.config import DB_POOL_SIZE, DB_MAX_OVERFLOW
    
    logger.info("Starting connection pool monitor...")
    check_interval = 60  # Check every 60 seconds
    max_idle_time = 300  # Reset pool if idle for 5 minutes
    
    while True:
        try:
            await asyncio.sleep(check_interval)
            
            status = get_pool_status()
            if "error" in status:
                logger.warning(f"Pool status check failed: {status['error']}")
                continue
            
            checked_out = status.get("checked_out", 0)
            overflow = status.get("overflow", 0)
            total = status.get("total", 0)
            
            # Log pool status
            logger.info(f"Pool status: {total} connections ({checked_out} active, {overflow} overflow)")
            
            # Alert if pool is getting exhausted
            pool_size = DB_POOL_SIZE + DB_MAX_OVERFLOW
            if total >= pool_size * 0.8:
                logger.warning(f"Connection pool near capacity: {total}/{pool_size} connections in use")
            
            # Proactive pool refresh if too many connections are checked out for too long
            if checked_out > DB_POOL_SIZE and overflow > 0:
                logger.info("High connection usage detected, connections will be recycled naturally")
            
            # Test connection health periodically
            try:
                with Session(engine) as test_session:
                    test_session.execute("SELECT 1")
                logger.debug("Connection health check passed")
            except Exception as health_error:
                logger.error(f"Connection health check failed: {health_error}")
                logger.info("Disposing connection pool due to failed health check")
                engine.dispose()
                
        except asyncio.CancelledError:
            logger.info("Connection pool monitor shutting down")
            break
        except Exception as e:
            logger.error(f"Error in connection pool monitor: {e}")
            # Continue monitoring even if there's an error