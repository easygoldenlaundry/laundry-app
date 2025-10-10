# app/sla.py
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select

from app.db import get_engine
from app.models import Order, Claim, Event
from app.sockets import socketio_server, model_to_dict

# --- Constants ---
SLA_CHECK_INTERVAL_SECONDS = 30
SLA_WARNING_WINDOW_MINUTES = 10
SLA_AUTO_COMPENSATE_MINUTES = 30
SLA_AUTO_COMPENSATE_AMOUNT = 50.00
TERMINAL_STATUSES = ["Delivered", "Closed", "Cancelled"]


async def broadcast_sla_alert(order_data: dict, sla_status: str):
    """
    Emits an 'sla.alert' event to the relevant hub room.
    """
    hub_id = order_data.get("hub_id")
    if not hub_id:
        return

    room = f"hub:{hub_id}"
    payload = {"order": order_data, "sla_status": sla_status}
    await socketio_server.emit('sla.alert', payload, room=room)
    logging.info(f"Broadcasted SLA alert for order {order_data['id']} to room {room} with status {sla_status}")


async def check_slas_periodically():
    """
    A background task that runs indefinitely to check order SLAs.
    """
    logging.info("--- Starting background SLA checker ---")
    engine = get_engine()

    while True:
        try:
            now = datetime.now(timezone.utc)
            
            with Session(engine) as session:
                orders_to_check = session.exec(
                    select(Order).where(
                        Order.sla_deadline != None,
                        Order.status.notin_(TERMINAL_STATUSES)
                    )
                ).all()

                for order in orders_to_check:
                    # Ensure the deadline from the DB is timezone-aware before comparison
                    sla_deadline_aware = order.sla_deadline
                    if sla_deadline_aware.tzinfo is None:
                        # If the datetime is naive, assume it's UTC
                        sla_deadline_aware = sla_deadline_aware.replace(tzinfo=timezone.utc)

                    # Nearing Breach: within the warning window but not yet breached
                    if (sla_deadline_aware - timedelta(minutes=SLA_WARNING_WINDOW_MINUTES)) < now < sla_deadline_aware:
                        await broadcast_sla_alert(model_to_dict(order), "nearing_breach")

                    # Breached: past the deadline
                    elif now > sla_deadline_aware:
                        await broadcast_sla_alert(model_to_dict(order), "breached")
                        
                        # Auto-Compensation: if breached by more than the threshold
                        if now > (sla_deadline_aware + timedelta(minutes=SLA_AUTO_COMPENSATE_MINUTES)):
                            existing_claim = session.exec(
                                select(Claim).where(
                                    Claim.order_id == order.id,
                                    Claim.claim_type == "delay"
                                )
                            ).first()
                            
                            if not existing_claim:
                                logging.warning(f"Order {order.id} breached SLA by >{SLA_AUTO_COMPENSATE_MINUTES}m. Auto-compensating.")
                                
                                new_claim = Claim(
                                    order_id=order.id,
                                    claim_type="delay",
                                    status="resolved",
                                    amount=SLA_AUTO_COMPENSATE_AMOUNT,
                                    resolved_at=now,
                                    notes=f"[Auto-resolved: SLA breached by more than {SLA_AUTO_COMPENSATE_MINUTES} minutes]"
                                )
                                session.add(new_claim)
                                
                                event = Event(
                                    order_id=order.id,
                                    to_status="SLA_Breach_Compensated",
                                    meta=f"Auto-compensated with R{SLA_AUTO_COMPENSATE_AMOUNT}"
                                )
                                session.add(event)
                                session.commit()

        except Exception as e:
            logging.error(f"Error in SLA checker loop: {e}", exc_info=True)

        await asyncio.sleep(SLA_CHECK_INTERVAL_SECONDS)