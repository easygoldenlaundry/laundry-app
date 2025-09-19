# app/db.py
from sqlmodel import create_engine, SQLModel, Session
from app.config import DB_PATH

# The connect_args is needed for SQLite to allow multiple threads to access it,
# which is what happens with FastAPI's dependencies.
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})

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