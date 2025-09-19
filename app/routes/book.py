# app/routes/book.py
import re
import secrets
import uuid
import logging
from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Depends, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.db import get_session
from app.models import Order, Item, Event, Bag, Setting, User, Customer
from app.sockets import broadcast_order_update
from app.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# --- THIS IS THE FIX: Redirect root to the booking page ---
@router.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/book")

@router.get("/book", response_class=HTMLResponse)
async def get_booking_form(request: Request, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Serves the customer-facing booking form."""
    price_setting = session.get(Setting, "price_per_load")
    price = price_setting.value if price_setting else "150.00"
    
    customer_profile = None
    if user and user.role == 'customer':
        customer_profile = session.exec(select(Customer).where(Customer.user_id == user.id)).first()

    return templates.TemplateResponse("book.html", {
        "request": request,
        "price_per_load": price,
        "customer": customer_profile
    })


@router.post("/book", response_class=RedirectResponse)
async def create_order_from_booking(
    request: Request,
    background_tasks: BackgroundTasks,
    customer_name: str = Form(...),
    customer_phone: str = Form(...),
    customer_address: str = Form(...),
    delivery_option: str = Form(...), # 'express' or 'next_day'
    notes_for_driver: Optional[str] = Form(None),
    external_id: str = Form(...),
    hub_id: int = Form(1),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """
    Handles the booking form submission, creating an order idempotently.
    Redirects to the tracking page for the created or existing order.
    """
    existing_order = session.exec(
        select(Order).where(Order.external_id == external_id)
    ).first()

    if existing_order:
        logging.warning(f"Duplicate booking submission for external_id: {external_id}. Redirecting to existing order {existing_order.id}.")
        return RedirectResponse(
            url=f"/track/{existing_order.tracking_token}", status_code=303
        )

    # Find the customer profile if the user is logged in
    customer_profile = None
    if user and user.role == 'customer':
        customer_profile = session.exec(select(Customer).where(Customer.user_id == user.id)).first()

    # --- Calculate SLA Deadline ---
    settings = {s.key: s.value for s in session.exec(select(Setting)).all()}
    now = datetime.now(timezone.utc)
    sla_deadline = None
    if delivery_option == "express":
        hours = int(settings.get("express_delivery_hours", 5))
        sla_deadline = now + timedelta(hours=hours)
    elif delivery_option == "next_day":
        hours = int(settings.get("next_day_delivery_hours", 24))
        sla_deadline = now + timedelta(hours=hours)

    # --- Generate PINs and Tracking ---
    sanitized_phone = re.sub(r"[^0-9+]", "", customer_phone)
    pickup_pin = str(secrets.randbelow(10000)).zfill(4)
    delivery_pin = str(secrets.randbelow(10000)).zfill(4)
    tracking_token = f"trk_{secrets.token_urlsafe(12)}"
    
    new_order = Order(
        external_id=external_id,
        tracking_token=tracking_token,
        customer_name=customer_name,
        customer_phone=sanitized_phone,
        customer_address=customer_address,
        hub_id=hub_id,
        status="Created",
        sla_deadline=sla_deadline,
        pickup_pin=pickup_pin,
        delivery_pin=delivery_pin,
        notes_for_driver=notes_for_driver,
        # Associate the order with the customer profile ID
        customer_id=customer_profile.id if customer_profile else None
    )
    session.add(new_order)
    session.commit()
    session.refresh(new_order)

    # Generate a random, unique bag code
    bag_code = f"BAG-{secrets.token_hex(4).upper()}"
    default_bag = Bag(order_id=new_order.id, bag_code=bag_code)
    session.add(default_bag)

    initial_event = Event(
        order_id=new_order.id,
        from_status=None,
        to_status="Created",
        meta=f"Created via web booking. external_id: {external_id}"
    )
    session.add(initial_event)
    
    session.commit()
    session.refresh(new_order)

    logging.info(f"New order created from web booking. Order ID: {new_order.id}, External ID: {external_id}")

    background_tasks.add_task(broadcast_order_update, new_order)

    return RedirectResponse(
        url=f"/track/{new_order.tracking_token}?new=true", status_code=303
    )