# app/routes/book.py
import re
import secrets
import uuid
import logging
import json
from typing import Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Request, Depends, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.db import get_session
from app.models import Order, Event, Bag, Setting, User, Customer
from app.sockets import broadcast_order_update
from app.auth import get_current_user, get_current_api_user
from app.security import signer
from app.services import capacity_planner

# Router for HTML-serving web pages
router = APIRouter()
# Router for JSON-serving mobile API
api_router = APIRouter(prefix="/api", tags=["Mobile Booking API"])

templates = Jinja2Templates(directory="app/templates")


@api_router.get("/mobile/pricing")
def get_mobile_pricing_estimate():
    """Simple pricing estimate for the mobile app."""
    return {"distance_km": 5.2, "pickup_cost": 50.0, "estimated_time": "15 minutes"}

@api_router.post("/orders/book")
async def create_booking_api(
    request: Request,
    background_tasks: BackgroundTasks,
    pickup_address: str = Form(...),
    pickup_latitude: float = Form(...),
    pickup_longitude: float = Form(...),
    phone: str = Form(...),
    processing_option: str = Form(...),
    terms_accepted: bool = Form(...),
    distance_km: Optional[float] = Form(None),
    pickup_cost: Optional[float] = Form(None),
    user: User = Depends(get_current_api_user),
    session: Session = Depends(get_session)
):
    """Creates a new booking from the mobile app, always returning JSON."""
    customer = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found")

    slots_data = capacity_planner.generate_availability_slots(session)
    price_per_load = slots_data["wait_and_save_price"] if processing_option != 'standard' else slots_data.get("slot", {}).get("price_per_load", 210.0)
    turnaround_hours = "Up to 48" if processing_option != 'standard' else slots_data.get("slot", {}).get("turnaround_hours", 12)
    sla_deadline = datetime.now(timezone.utc) + timedelta(hours=48) if processing_option != 'standard' else datetime.fromisoformat(slots_data['slot']['timestamp'])

    # Update customer location from booking
    customer.address = pickup_address
    customer.latitude = pickup_latitude
    customer.longitude = pickup_longitude
    session.add(customer)

    new_order = Order(
        external_id=f"mob-{uuid.uuid4()}", tracking_token=f"trk_{secrets.token_urlsafe(12)}",
        customer_name=customer.full_name, customer_phone=phone, customer_address=pickup_address,
        hub_id=1, status="Created", customer_id=customer.id, sla_deadline=sla_deadline,
        distance_km=distance_km,
        pickup_cost=pickup_cost
    )
    session.add(new_order)
    session.commit(); session.refresh(new_order)

    # Common post-creation logic
    bag = Bag(order_id=new_order.id, bag_code=f"BAG-{secrets.token_hex(4).upper()}")
    event = Event(order_id=new_order.id, to_status="Created", meta="Created via mobile booking.")
    session.add_all([bag, event])
    session.commit(); session.refresh(new_order)
    background_tasks.add_task(broadcast_order_update, new_order)

    order_dict = new_order.dict()
    order_dict.update({
        "processing_time": f"~{turnaround_hours} hr", "price_per_load": price_per_load, "pickup_cost": pickup_cost,
    })
    return JSONResponse(content={"order": order_dict, "message": "Booking created successfully"})


# --- Existing Web Endpoints (HTML only) ---

@router.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/book")

@router.get("/api/booking/availability")
def get_booking_availability(session: Session = Depends(get_session)):
    """API endpoint for the web booking page."""
    try:
        return capacity_planner.generate_availability_slots(session)
    except Exception as e:
        logging.error(f"Error generating availability slots: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not calculate availability.")

@router.get("/book", response_class=HTMLResponse)
async def get_booking_form(request: Request, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    """Serves the customer-facing web booking form."""
    customer_profile = session.exec(select(Customer).where(Customer.user_id == user.id)).first() if user else None
    hero_data = {"turnaround": "3+", "pickup": "under 60", "insurance": "5,000"} # Default
    try:
        settings = capacity_planner.get_settings_as_dict(session)
        hero_data["turnaround"] = round(capacity_planner.get_base_turnaround_seconds(settings) / 3600, 1)
    except Exception: pass
    return templates.TemplateResponse("book.html", {"request": request, "customer": customer_profile, "hero_data": hero_data})

@router.post("/book")
async def create_order_from_booking_web(
    request: Request, background_tasks: BackgroundTasks, customer_name: str = Form(...),
    customer_phone: str = Form(...), customer_address: str = Form(...), selected_slot_timestamp: str = Form(...),
    is_wait_and_save: bool = Form(False), notes_for_driver: Optional[str] = Form(None), external_id: str = Form(...),
    hub_id: int = Form(1), user: User = Depends(get_current_user), session: Session = Depends(get_session)
):
    """Handles the web booking form submission."""
    if not user:
        booking_data = { "customer_name": customer_name, "customer_phone": customer_phone, "customer_address": customer_address, "selected_slot_timestamp": selected_slot_timestamp, "is_wait_and_save": is_wait_and_save, "notes_for_driver": notes_for_driver, "external_id": external_id, "hub_id": hub_id }
        signed_data = signer.sign(json.dumps(booking_data).encode('utf-8')).decode('utf-8')
        response = RedirectResponse(url="/register/customer", status_code=303)
        response.set_cookie(key="pending_booking", value=signed_data, httponly=True, max_age=900)
        return response
    
    existing_order = session.exec(select(Order).where(Order.external_id == external_id)).first()
    if existing_order:
        return RedirectResponse(url=f"/track/{existing_order.tracking_token}", status_code=303)

    customer_profile = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    sla_deadline = datetime.now(timezone.utc) + timedelta(hours=48) if is_wait_and_save else datetime.fromisoformat(selected_slot_timestamp)
    
    new_order = Order(
        external_id=external_id, tracking_token=f"trk_{secrets.token_urlsafe(12)}", customer_name=customer_name,
        customer_phone=customer_phone, customer_address=customer_address, hub_id=hub_id, status="Created",
        sla_deadline=sla_deadline, notes_for_driver=notes_for_driver, customer_id=customer_profile.id if customer_profile else None
    )
    session.add(new_order)
    session.commit(); session.refresh(new_order)

    bag = Bag(order_id=new_order.id, bag_code=f"BAG-{secrets.token_hex(4).upper()}")
    event = Event(order_id=new_order.id, to_status="Created", meta=f"Created via web booking.")
    session.add_all([bag, event])
    session.commit(); session.refresh(new_order)
    background_tasks.add_task(broadcast_order_update, new_order)

    return RedirectResponse(url=f"/track/{new_order.tracking_token}?new=true", status_code=303)