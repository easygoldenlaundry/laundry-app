# app/services/dispatch.py
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from app.models import Order, Driver, User
from app.services.state_machine import apply_transition
from app.services.notifications import notification_service
import asyncio

def dispatch_delivery_for_order(session: Session, order: Order, user_id: int):
    """
    Moves an order to the 'ReadyForDelivery' queue after it passes QA.
    It waits for customer confirmation and clears any previous driver assignment.
    """
    if order.status != "QA":
        # We only dispatch from the QA station.
        return

    # When an order passes QA, it no longer belongs to the original pickup driver.
    # Clearing this ID makes it available to ANY driver once the customer requests delivery.
    order.assigned_driver_id = None
    session.add(order)
    
    meta = {
        "qa_passed_by": user_id,
        "delivery_status": "awaiting_customer_request"
    }

    print(f"Order {order.id} passed QA. Clearing driver and moving to ReadyForDelivery queue.")

    # Transition the order to the ReadyForDelivery state.
    updated_order = apply_transition(session, order, "ReadyForDelivery", user_id=user_id, meta=meta)

    # Send ready for delivery notification
    order_dict = updated_order.dict()
    asyncio.create_task(notification_service.send_ready_for_delivery_notification(order_dict))