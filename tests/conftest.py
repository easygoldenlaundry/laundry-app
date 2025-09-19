# tests/conftest.py
import asyncio
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

from app.db import get_session
from app.main import app

@pytest.fixture(name="session")
def session_fixture() -> Generator[Session, None, None]:
    """
    Creates an in-memory SQLite database session for each test.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)

@pytest_asyncio.fixture(name="client")
async def client_fixture(session: Session, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[AsyncClient, None]:
    """
    Creates an AsyncClient that uses the test database session and mocks noisy functions.
    """
    # --- THIS IS THE FIX ---
    # Create a dummy async function to replace the real one.
    async def mock_broadcast_order_update(order):
        pass  # Do nothing during tests

    # Use monkeypatch to replace the real function with our dummy one for all tests.
    monkeypatch.setattr("app.services.state_machine.broadcast_order_update", mock_broadcast_order_update)
    # --- END OF FIX ---

    def get_session_override() -> Session:
        return session

    app.dependency_overrides[get_session] = get_session_override
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()

@pytest.fixture(scope="session")
def event_loop():
    """
    Creates an event loop for the entire test session.
    Prevents `RuntimeError: Event loop is closed` on Windows.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()