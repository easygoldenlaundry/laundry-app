# app/db.py
import os
from dotenv import load_dotenv
from sqlmodel import create_engine, SQLModel, Session

# Load environment variables from .env file
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable not set.")

# For Supabase/PostgreSQL, we don't need 'check_same_thread'
engine = create_engine(DATABASE_URL)

def get_engine():
    """Returns the global engine instance."""
    return engine

def get_session():
    """FastAPI dependency to get a DB session."""
    with Session(engine) as session:
        yield session

def create_db_and_tables():
    """Creates the database and all tables if they don't exist."""
    # Import models here to prevent circular import issues
    from . import models
    SQLModel.metadata.create_all(engine)