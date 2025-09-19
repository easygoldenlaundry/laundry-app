# tests/test_driver_accept_race.py
import asyncio
import json
import pytest
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlmodel import Session

from app.models import Order, User
from app.security import signer

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio

def create_driver_session_cookie(user: User) -> str:
    """Helper to create a valid session cookie for a driver."""
    expires = datetime.now(timezone.utc) + timedelta(days=1)
    session_data = {"user_id": user.id, "role": user.role, "expires_at": expires.isoformat()}
    return signer.sign(json.dumps(session_data).encode()).decode()

async def test_driver_accept_race_condition(client: AsyncClient, session: Session):
    """
    GIVEN an available order and two drivers
    WHEN both drivers try to accept the order at the same time
    THEN one driver succeeds (200 OK) and the other fails (409 Conflict)
    """
    # GIVEN an available order and two drivers
    order = Order(
        external_id="race_order_1",
        tracking_token="race_token_1",
        customer_name="Racy McRacerson",
        customer_phone="555-RACE",
        customer_address="123 Race Track",
        status="Created"
    )
    driver1 = User(username="driver_r1", role="driver", display_name="Driver One")
    driver2 = User(username="driver_r2", role="driver", display_name="Driver Two")
    session.add_all([order, driver1, driver2])
    session.commit()
    session.refresh(order)
    session.refresh(driver1)
    session.refresh(driver2)

    cookie1 = create_driver_session_cookie(driver1)
    cookie2 = create_driver_session_cookie(driver2)

    # WHEN both drivers try to accept concurrently
    async def attempt_accept(user: User, cookie: str):
        return await client.post(
            f"/api/drivers/{user.id}/accept",
            json={"order_id": order.id},
            cookies={"session_user": cookie}
        )

    results = await asyncio.gather(
        attempt_accept(driver1, cookie1),
        attempt_accept(driver2, cookie2)
    )

    # THEN one succeeds and one fails
    status_codes = sorted([res.status_code for res in results])
    assert status_codes == [200, 409]

    # AND the database reflects the winner
    session.refresh(order)
    winner_response = results[0] if results[0].status_code == 200 else results[1]
    winner_id = winner_response.json()["assigned_driver_id"]

    assert order.status == "AssignedToDriver"
    assert order.assigned_driver_id == winner_id