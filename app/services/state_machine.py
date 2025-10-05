# app/services/state_machine.py
import logging
from datetime import datetime, timezone
from sqlmodel import Session
from app.models import Order, Event
from app.sockets import broadcast_order_update
import asyncio

ALLOWED_TRANSITIONS = {
    "Created": ["AssignedToDriver", "PickedUp"],
    "AssignedToDriver": ["PickedUp"],
    "PickedUp": ["DeliveredToHub", "AtHub"],
    "DeliveredToHub": ["AtHub", "Imaging"],
    "AtHub": ["Imaging"],
    "Imaging": ["Processing"],
    "Pretreat": ["Washing"], 
    "Washing": ["Drying"],  
    "Drying": ["Folding"],  
    "Folding": ["QA"],      
    "Processing": ["QA"],
    "QA": ["ReadyForDelivery", "Processing"], 
    "ReadyForDelivery": ["OutForDelivery"],
    "OutForDelivery": ["OnRouteToCustomer"],
    "OnRouteToCustomer": ["Delivered"],
    "Delivered": ["Closed", "Pretreat"],
}

# Mapping from status to the timestamp field that should be set
STATUS_TO_TIMESTAMP_FIELD = {
    "PickedUp": "picked_up_at",
    "DeliveredToHub": "at_hub_at",
    "AtHub": "at_hub_at",
    "Imaging": "imaging_started_at",
    "Processing": "processing_started_at",
    "QA": "qa_started_at",
    "ReadyForDelivery": "ready_for_delivery_at",
    "OutForDelivery": "out_for_delivery_at",
    "Delivered": "delivered_at",
    "Closed": "closed_at",
}


def validate_transition(order: Order, to_status: str):
    if to_status not in ALLOWED_TRANSITIONS.get(order.status, []):
        raise ValueError(f"Illegal transition from '{order.status}' to '{to_status}'")

def apply_transition(session: Session, order: Order, to_status: str, user_id: int = None, meta: dict = None) -> Order:
    if order.status == to_status:
        return order

    logging.info(f"Transitioning Order ID {order.id} from '{order.status}' to '{to_status}' (user_id: {user_id})")
    validate_transition(order, to_status)

    event = Event(
        order_id=order.id,
        from_status=order.status,
        to_status=to_status,
        user_id=user_id,
        meta=str(meta) if meta else None,
    )
    session.add(event)

    # --- [MODIFIED] Logic to set timestamps ---
    now = datetime.now(timezone.utc)
    timestamp_field = STATUS_TO_TIMESTAMP_FIELD.get(to_status)
    if timestamp_field and getattr(order, timestamp_field) is None:
        setattr(order, timestamp_field, now)
    
    order.status = to_status
    order.updated_at = now
    session.add(order)

    session.commit()
    session.refresh(order)

    # --- THIS IS THE FIX ---
    # Use create_task on the running event loop instead of asyncio.run()
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(broadcast_order_update(order))
    except RuntimeError:
        # This is a fallback for when the function is called from a context without a running loop
        asyncio.run(broadcast_order_update(order))

    return order