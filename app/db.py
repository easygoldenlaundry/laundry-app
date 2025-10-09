# app/db.py
import os
from dotenv import load_dotenv
from sqlmodel import create_engine, SQLModel, Session
from app.config import DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_POOL_TIMEOUT, DB_POOL_RECYCLE, IS_PRODUCTION

# Load environment variables from .env file
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable not set.")

# Optimized engine configuration for Supabase/PostgreSQL
# This configuration helps prevent "max clients reached" errors
engine = create_engine(
    DATABASE_URL,
    # Connection pool settings to prevent connection exhaustion
    pool_size=DB_POOL_SIZE,           # Environment-aware pool size
    max_overflow=DB_MAX_OVERFLOW,     # Environment-aware max overflow
    pool_timeout=DB_POOL_TIMEOUT,     # Seconds to wait for a connection from the pool
    pool_recycle=DB_POOL_RECYCLE,     # Recycle connections (environment-aware)
    pool_pre_ping=True,               # Validate connections before use
    # Additional PostgreSQL optimizations
    connect_args={
        "options": "-c timezone=utc"  # Ensure UTC timezone
    },
    # Echo SQL queries in development for debugging
    echo=not IS_PRODUCTION
)

def get_engine():
    """Returns the global engine instance."""
    return engine

def get_session():
    """FastAPI dependency to get a DB session."""
    with Session(engine) as session:
        yield session

def create_db_and_tables(max_retries=5, retry_delay=5):
    """Creates the database and all tables if they don't exist."""
    import time
    import logging

    logger = logging.getLogger(__name__)

    # Import models here to prevent circular import issues
    from . import models

    for attempt in range(max_retries):
        try:
            logger.info(f"Attempting to create database tables (attempt {attempt + 1}/{max_retries})")
            SQLModel.metadata.create_all(engine)
            logger.info("Database tables created successfully")
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