# app/routes/users.py
import re
import secrets
import uuid
import json
from typing import Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import User, Customer, Order, Bag, Setting, Event
from app.auth import get_password_hash, create_access_token, get_current_user
from app.security import signer
from app.sockets import broadcast_order_update
from starlette.responses import Response

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    display_name: str
    role: str # 'driver', 'staff'

@router.post("/register", include_in_schema=False)
async def handle_staff_registration(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(...),
    role: str = Form(...),
    session: Session = Depends(get_session)
):
    """Endpoint for staff/drivers to register. They will be inactive until approved."""
    existing_user = session.exec(
        select(User).where((User.username == username) | (User.email == email))
    ).first()
    if existing_user:
        return templates.TemplateResponse("register.html", {
            "request": request, "error": "Username or email already registered."
        }, status_code=409)

    hashed_password = get_password_hash(password)
    new_user = User(
        username=username,
        email=email,
        hashed_password=hashed_password,
        display_name=display_name,
        role=role,
        is_active=False # Staff/drivers must be approved
    )
    session.add(new_user)
    session.commit()
    
    # --- THIS IS THE FIX: Pass username to the template to pre-fill the login form ---
    return templates.TemplateResponse("login.html", {
        "request": request, 
        "success": "Registration successful! Please wait for an admin to approve your account.",
        "prefill_username": username
    })


@router.post("/register/customer", include_in_schema=False)
async def handle_customer_registration(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    phone_number: str = Form(...),
    address: str = Form(...),
    pending_booking: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    """
    Endpoint for customers to register. They are active immediately and logged in.
    If a pending booking exists, it creates the order after registration.
    """
    existing_user = session.exec(select(User).where(User.email == email)).first()
    if existing_user:
        return templates.TemplateResponse("register_customer.html", {
            "request": request, "error": "Email is already registered."
        }, status_code=409)

    hashed_password = get_password_hash(password)
    
    new_user = User(
        username=email,
        email=email,
        hashed_password=hashed_password,
        display_name=full_name,
        role="customer",
        is_active=True
    )
    session.add(new_user)
    session.commit()
    session.refresh(new_user)

    new_customer_profile = Customer(
        user_id=new_user.id,
        full_name=full_name,
        phone_number=phone_number,
        address=address
    )
    session.add(new_customer_profile)
    session.commit()
    session.refresh(new_customer_profile)
    
    redirect_url = "/account" # Default redirect after registration

    if pending_booking:
        try:
            unsigned_data = signer.unsign(pending_booking).decode('utf-8')
            booking_data = json.loads(unsigned_data)

            settings = {s.key: s.value for s in session.exec(select(Setting)).all()}
            now = datetime.now(timezone.utc)
            sla_deadline = None
            if booking_data["delivery_option"] == "express":
                hours = int(settings.get("express_delivery_hours", 5))
                sla_deadline = now + timedelta(hours=hours)
            elif booking_data["delivery_option"] == "next_day":
                hours = int(settings.get("next_day_delivery_hours", 24))
                sla_deadline = now + timedelta(hours=hours)

            new_order = Order(
                external_id=booking_data["external_id"],
                tracking_token=f"trk_{secrets.token_urlsafe(12)}",
                customer_name=booking_data["customer_name"],
                customer_phone=re.sub(r"[^0-9+]", "", booking_data["customer_phone"]),
                customer_address=booking_data["customer_address"],
                hub_id=booking_data["hub_id"],
                status="Created",
                sla_deadline=sla_deadline,
                pickup_pin=str(secrets.randbelow(10000)).zfill(4),
                delivery_pin=str(secrets.randbelow(10000)).zfill(4),
                notes_for_driver=booking_data["notes_for_driver"],
                customer_id=new_customer_profile.id
            )
            session.add(new_order)
            session.commit()
            session.refresh(new_order)

            bag_code = f"BAG-{secrets.token_hex(4).upper()}"
            default_bag = Bag(order_id=new_order.id, bag_code=bag_code)
            session.add(default_bag)

            initial_event = Event(order_id=new_order.id, to_status="Created", meta=f"Created via web booking after registration.")
            session.add(initial_event)
            session.commit()
            session.refresh(new_order)
            
            # Since an order was created, redirect to its tracking page
            redirect_url = f"/track/{new_order.tracking_token}?new=true"

        except Exception as e:
            # If cookie is bad, log it and proceed with normal login
            print(f"Error processing pending booking after registration: {e}")
    
    access_token = create_access_token(data={"sub": new_user.username})
    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    response.delete_cookie("pending_booking") # Clear the cookie
    return response


# HTML Pages for Registration
@router.get("/register", response_class=HTMLResponse, include_in_schema=False)
async def get_registration_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.get("/register/customer", response_class=HTMLResponse, include_in_schema=False)
async def get_customer_registration_page(request: Request):
    # --- THIS IS THE FIX: Check for pending booking data in cookie ---
    booking_data = None
    pending_booking_cookie = request.cookies.get("pending_booking")
    if pending_booking_cookie:
        try:
            unsigned_data = signer.unsign(pending_booking_cookie).decode('utf-8')
            booking_data = json.loads(unsigned_data)
        except Exception:
            booking_data = None # Ignore if invalid
            
    return templates.TemplateResponse("register_customer.html", {
        "request": request,
        "booking_data": booking_data
    })

# --- NEW: Routes for customer account management ---
def get_current_customer_user(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to ensure the user is a customer."""
    if not current_user or current_user.role != 'customer':
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            detail="Not a customer",
            headers={"Location": "/login"}
        )
    return current_user

@router.get("/account", response_class=HTMLResponse)
def get_customer_account_page(
    request: Request,
    user: User = Depends(get_current_customer_user),
    session: Session = Depends(get_session)
):
    """Serves the customer account page with their orders and details."""
    customer_profile = session.exec(
        select(Customer).where(Customer.user_id == user.id)
    ).first()
    
    if not customer_profile:
        # This case should ideally not happen if registration is done correctly
        raise HTTPException(status_code=404, detail="Customer profile not found")

    orders = session.exec(
        select(Order)
        .where(Order.customer_id == customer_profile.id)
        .order_by(Order.created_at.desc())
    ).all()
    
    return templates.TemplateResponse("account.html", {
        "request": request,
        "customer": customer_profile,
        "orders": orders
    })

@router.post("/account/update")
def update_customer_details(
    request: Request,
    full_name: str = Form(...),
    phone_number: str = Form(...),
    address: str = Form(...),
    user: User = Depends(get_current_customer_user),
    session: Session = Depends(get_session)
):
    """Handles the form submission for updating customer details."""
    customer_profile = session.exec(
        select(Customer).where(Customer.user_id == user.id)
    ).first()
    
    if not customer_profile:
        raise HTTPException(status_code=404, detail="Customer profile not found")
        
    customer_profile.full_name = full_name
    customer_profile.phone_number = phone_number
    customer_profile.address = address
    session.add(customer_profile)
    session.commit()
    
    return RedirectResponse(url="/account", status_code=303)