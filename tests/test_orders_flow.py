# tests/test_orders_flow.py
import json
import pytest
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlmodel import Session, select

from app.models import Order, Event, User
from app.security import signer

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio

def create_driver_session_cookie(user: User) -> str:
    """Helper to create a valid session cookie for a driver."""
    expires = datetime.now(timezone.utc) + timedelta(days=1)
    session_data = {"user_id": user.id, "role": user.role, "expires_at": expires.isoformat()}
    return signer.sign(json.dumps(session_data).encode()).decode()

async def test_order_creation_and_lifecycle(client: AsyncClient, session: Session):
    """
    Tests the primary order flow from booking to hub intake.
    """
    # 1. Create Order via /book endpoint
    form_data = {
        "customer_name": "John Doe",
        "customer_phone": "555-1234",
        "customer_address": "123 Main St",
        "items_text": "Blue Shirt\nRed Dress",
        "external_id": "test_order_flow_1",
        "hub_id": 1
    }
    # --- THIS IS THE FIX ---
    response = await client.post("/book", data=form_data, follow_redirects=False)
    # --- END OF FIX ---
    assert response.status_code == 303 # Redirect
    
    # Verify order was created in DB
    order = session.exec(select(Order).where(Order.external_id == "test_order_flow_1")).one()
    assert order.customer_name == "John Doe"
    assert order.status == "Created"
    assert order.total_items == 2
    
    # Verify "Created" event was logged
    created_event = session.exec(select(Event).where(Event.order_id == order.id, Event.to_status == "Created")).one()
    assert created_event is not None

    # Test Idempotency: submitting the same form again redirects to the same order
    response2 = await client.post("/book", data=form_data, follow_redirects=False)
    assert response2.status_code == 303
    # The second redirect will not have '?new=true', so check if its location is a part of the first one.
    assert response2.headers["location"] in response.headers["location"]


    # 2. Assign to Driver
    driver = User(username="test_driver", role="driver", display_name="Test Driver")
    session.add(driver)
    session.commit()
    session.refresh(driver)
    
    driver_cookie = create_driver_session_cookie(driver)
    
    response = await client.post(
        f"/api/drivers/{driver.id}/accept",
        json={"order_id": order.id},
        cookies={"session_user": driver_cookie}
    )
    assert response.status_code == 200
    session.refresh(order)
    assert order.status == "AssignedToDriver"
    assert order.assigned_driver_id == driver.id
    
    assigned_event = session.exec(select(Event).where(Event.order_id == order.id, Event.to_status == "AssignedToDriver")).one()
    assert assigned_event is not None

    # 3. Mark as Picked Up
    response = await client.post(
        f"/api/drivers/{driver.id}/picked_up",
        data={"order_id": order.id},
        cookies={"session_user": driver_cookie}
    )
    assert response.status_code == 200
    session.refresh(order)
    assert order.status == "PickedUp"

    # 4. Mark as Delivered to Hub
    response = await client.post(
        f"/api/drivers/{driver.id}/delivered_to_hub",
        data={"order_id": order.id},
        cookies={"session_user": driver_cookie}
    )
    assert response.status_code == 200
    session.refresh(order)
    assert order.status == "DeliveredToHub"

    # 5. Scan Bag at Hub Intake
    bag_code = f"BAG-ORDER{order.id}"
    response = await client.post(
        "/api/bags/scan",
        json={"order_id": order.id, "bag_code": bag_code, "user_id": 1}
    )
    assert response.status_code == 200
    session.refresh(order)
    assert order.status == "Imaging"

    imaging_event = session.exec(select(Event).where(Event.order_id == order.id, Event.to_status == "Imaging")).one()
    assert imaging_event is not None