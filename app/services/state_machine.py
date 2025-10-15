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
    """
    Applies a state transition to an order with proper transaction handling.
    Returns the updated order. Broadcasts are queued to happen after commit.
    """
    if order.status == to_status:
        return order

    logging.info(f"Transitioning Order ID {order.id} from '{order.status}' to '{to_status}' (user_id: {user_id})")
    
    try:
        validate_transition(order, to_status)
    except ValueError as e:
        logging.error(f"Invalid transition for order {order.id}: {e}")
        raise

    event = Event(
        order_id=order.id,
        from_status=order.status,
        to_status=to_status,
        user_id=user_id,
        meta=str(meta) if meta else None,
    )
    session.add(event)

    # --- Logic to set timestamps ---
    now = datetime.now(timezone.utc)
    timestamp_field = STATUS_TO_TIMESTAMP_FIELD.get(to_status)
    if timestamp_field and getattr(order, timestamp_field) is None:
        setattr(order, timestamp_field, now)
    
    order.status = to_status
    order.updated_at = now
    session.add(order)

    try:
        session.commit()
        session.refresh(order)
        logging.info(f"Order {order.id} transitioned to '{to_status}' successfully")
    except Exception as e:
        logging.error(f"Failed to commit transition for order {order.id}: {e}")
        session.rollback()
        raise

    # --- CRITICAL FIX: Schedule broadcast AFTER successful commit ---
    # This prevents broadcasts from happening if the transaction fails
    # and avoids mixing async operations with database transactions
    _schedule_broadcast(order)

    return order

def _schedule_broadcast(order: Order):
    """
    Safely schedules a broadcast update for an order.
    Works from both sync and async contexts.
    """
    try:
        # Try to get the running event loop (async context)
        loop = asyncio.get_running_loop()
        # Schedule the broadcast as a task
        loop.create_task(broadcast_order_update(order))
        logging.debug(f"Scheduled broadcast for order {order.id} in async context")
    except RuntimeError:
        # No running loop (sync context) - create a new loop in a thread
        import threading
        def run_in_thread():
            try:
                asyncio.run(broadcast_order_update(order))
                logging.debug(f"Broadcast completed for order {order.id} in sync context")
            except Exception as e:
                logging.error(f"Failed to broadcast order update for {order.id}: {e}")
        
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()