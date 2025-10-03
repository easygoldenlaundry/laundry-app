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
from app.models import Order, Item, Event, Bag, Setting, User, Customer
from app.sockets import broadcast_order_update
from app.auth import get_current_user
from app.security import signer
from app.services import capacity_planner

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def wants_json(request: Request) -> bool:
    accept_header = request.headers.get("accept", "")
    return "application/json" in accept_header

@router.get("/api/mobile/pricing")
def get_mobile_pricing_estimate():
    """Simple pricing estimate for the mobile app."""
    return {
        "distance_km": 5.2, # Placeholder
        "pickup_cost": 50.0, # Placeholder
        "estimated_time": "15 minutes" # Placeholder
    }

@router.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/book")

@router.get("/api/booking/availability")
def get_booking_availability(session: Session = Depends(get_session)):
    """API endpoint to provide dynamic pricing and availability slots to the booking page."""
    try:
        slots_data = capacity_planner.generate_availability_slots(session)
        return slots_data
    except Exception as e:
        logging.error(f"Error generating availability slots: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Could not calculate availability.")

@router.get("/book", response_class=HTMLResponse)
async def get_booking_form(request: Request, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    # ... (this function remains unchanged)
    customer_profile = None
    if user and user.role == 'customer':
        customer_profile = session.exec(select(Customer).where(Customer.user_id == user.id)).first()

    try:
        settings = capacity_planner.get_settings_as_dict(session)
        base_turnaround_seconds = capacity_planner.get_base_turnaround_seconds(settings)
        min_turnaround_hours = round(base_turnaround_seconds / 3600, 1)
        
        hero_data = {
            "turnaround": min_turnaround_hours,
            "pickup": "under 60",
            "insurance": "5,000"
        }
    except Exception:
        hero_data = {
            "turnaround": "3+",
            "pickup": "under 60",
            "insurance": "5,000"
        }

    return templates.TemplateResponse("book.html", {
        "request": request,
        "customer": customer_profile,
        "hero_data": hero_data
    })


@router.post("/book")
async def create_order_from_booking(
    request: Request,
    background_tasks: BackgroundTasks,
    # Web form fields
    customer_name: Optional[str] = Form(None),
    customer_address: Optional[str] = Form(None),
    selected_slot_timestamp: Optional[str] = Form(None),
    is_wait_and_save: Optional[bool] = Form(None),
    notes_for_driver: Optional[str] = Form(None),
    external_id: Optional[str] = Form(None),
    hub_id: Optional[int] = Form(None),
    # Mobile form fields
    pickup_address: Optional[str] = Form(None),
    pickup_latitude: Optional[float] = Form(None),
    pickup_longitude: Optional[float] = Form(None),
    phone: Optional[str] = Form(None),
    processing_option: Optional[str] = Form(None),
    # Common fields
    customer_phone: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    """Handles booking from both web and mobile, returning the appropriate response."""
    is_json_request = wants_json(request)

    if not user:
        # This should not happen for mobile, as it requires auth.
        # This logic is for web users who are not logged in.
        # ... (existing web redirect to register logic)
        booking_data = { "customer_name": customer_name, "customer_phone": customer_phone, "customer_address": customer_address, "selected_slot_timestamp": selected_slot_timestamp, "is_wait_and_save": is_wait_and_save, "notes_for_driver": notes_for_driver, "external_id": external_id, "hub_id": hub_id }
        signed_data = signer.sign(json.dumps(booking_data).encode('utf-8')).decode('utf-8')
        response = RedirectResponse(url="/register/customer", status_code=303)
        response.set_cookie(key="pending_booking", value=signed_data, httponly=True, max_age=900)
        return response

    customer_profile = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer_profile:
        raise HTTPException(status_code=404, detail="Customer profile not found")

    if is_json_request:
        # --- MOBILE APP LOGIC ---
        slots_data = capacity_planner.generate_availability_slots(session)
        price_per_load = slots_data.get("slot", {}).get("price_per_load", 210.0)
        turnaround_hours = slots_data.get("slot", {}).get("turnaround_hours", 12)
        
        customer_profile.address = pickup_address
        customer_profile.latitude = pickup_latitude
        customer_profile.longitude = pickup_longitude
        session.add(customer_profile)

        new_order = Order(
            external_id=f"mob-{uuid.uuid4()}", tracking_token=f"trk_{secrets.token_urlsafe(12)}",
            customer_name=customer_profile.full_name, customer_phone=phone,
            customer_address=pickup_address, hub_id=1, status="Created",
            customer_id=customer_profile.id,
            sla_deadline=datetime.fromisoformat(slots_data['slot']['timestamp']) if processing_option == 'standard' else datetime.now(timezone.utc) + timedelta(hours=48)
        )
    else:
        # --- WEB APP LOGIC ---
        existing_order = session.exec(select(Order).where(Order.external_id == external_id)).first()
        if existing_order:
            return RedirectResponse(url=f"/track/{existing_order.tracking_token}", status_code=303)

        sla_deadline = datetime.fromisoformat(selected_slot_timestamp) if selected_slot_timestamp else datetime.now(timezone.utc) + timedelta(hours=48)
        new_order = Order(
            external_id=external_id, tracking_token=f"trk_{secrets.token_urlsafe(12)}",
            customer_name=customer_name, customer_phone=customer_phone, customer_address=customer_address,
            hub_id=hub_id, status="Created", sla_deadline=sla_deadline, notes_for_driver=notes_for_driver,
            customer_id=customer_profile.id
        )

    session.add(new_order)
    session.commit()
    session.refresh(new_order)

    # Common post-creation logic
    bag = Bag(order_id=new_order.id, bag_code=f"BAG-{secrets.token_hex(4).upper()}")
    event = Event(order_id=new_order.id, to_status="Created", meta="Created via booking.")
    session.add_all([bag, event])
    session.commit()
    session.refresh(new_order)
    
    background_tasks.add_task(broadcast_order_update, new_order)

    if is_json_request:
        # Return JSON for mobile
        order_dict = new_order.dict()
        order_dict.update({
            "processing_time": f"~{turnaround_hours} hr",
            "price_per_load": price_per_load,
            "pickup_cost": 50.0, # Placeholder
        })
        return JSONResponse(content={
            "order": order_dict,
            "message": "Booking created successfully"
        })
    else:
        # Return redirect for web
        return RedirectResponse(url=f"/track/{new_order.tracking_token}?new=true", status_code=303)