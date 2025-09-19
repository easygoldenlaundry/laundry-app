# tests/test_db_seed.py
import os
import pytest
from sqlmodel import Session, select
from app.db import get_engine
from app.models import Order
from app.seed_db import seed_database

DB_PATH = "brain.db"

@pytest.fixture(scope="module", autouse=True)
def setup_and_teardown_db():
    # Remove the DB file before the test if it exists
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    # Run the seed script
    seed_database()

    yield # This is where the testing happens

    # Teardown:
    # First, get the engine and explicitly close all connections.
    # This is the key to releasing the file lock on Windows.
    engine = get_engine()
    engine.dispose()

    # Now, remove the database file after tests are done
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)


def test_seed_creates_orders():
    """
    Tests that the seed script creates at least 3 orders.
    """
    engine = get_engine()
    with Session(engine) as session:
        statement = select(Order)
        orders = session.exec(statement).all()

        assert len(orders) >= 3
        print(f"\nFound {len(orders)} orders in the database.")