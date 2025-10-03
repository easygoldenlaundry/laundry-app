# app/routes/users.py
import re
import secrets
import uuid
import json
from typing import Optional, List
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
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

def wants_json(request: Request) -> bool:
    """Check if the client's Accept header prefers a JSON response."""
    accept_header = request.headers.get("accept", "")
    return "application/json" in accept_header

class UserProfile(BaseModel):
    id: int
    name: str
    email: str
    phone: Optional[str]
    whatsapp: Optional[str]
    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    role: str
    created_at: Optional[datetime]

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile

# ... (Staff registration endpoint is unchanged)
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
        is_active=False
    )
    session.add(new_user)
    session.commit()
    
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
    whatsapp_number: Optional[str] = Form(None),
    pending_booking: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    """
    Handles customer registration for both web and mobile.
    - Returns JSON for mobile apps.
    - Returns redirects for web, handling pending bookings.
    """
    is_json_request = wants_json(request)
    
    existing_user = session.exec(select(User).where(User.email == email)).first()
    if existing_user:
        if is_json_request:
            raise HTTPException(status_code=409, detail="Email is already registered")
        return templates.TemplateResponse("register_customer.html", {
            "request": request, "error": "Email is already registered."
        }, status_code=409)

    hashed_password = get_password_hash(password)
    
    new_user = User(
        username=email, email=email, hashed_password=hashed_password,
        display_name=full_name, role="customer", is_active=True
    )
    session.add(new_user)
    session.commit()
    session.refresh(new_user)

    new_customer = Customer(
        user_id=new_user.id, full_name=full_name, phone_number=phone_number,
        address=address, whatsapp_number=whatsapp_number
    )
    session.add(new_customer)
    session.commit()
    session.refresh(new_customer)
    
    access_token = create_access_token(data={"sub": new_user.username})

    if is_json_request:
        user_profile = UserProfile(
            id=new_user.id, name=new_customer.full_name, email=new_user.email,
            phone=new_customer.phone_number, whatsapp=new_customer.whatsapp_number,
            address=new_customer.address, latitude=new_customer.latitude, longitude=new_customer.longitude,
            role=new_user.role, created_at=new_user.created_at
        )
        return TokenResponse(access_token=access_token, user=user_profile)

    # --- Web-specific logic for redirects and pending bookings ---
    redirect_url = "/account"
    if pending_booking:
        # ... (existing web logic for pending bookings)
        try:
            unsigned_data = signer.unsign(pending_booking).decode('utf-8')
            booking_data = json.loads(unsigned_data)
            # ... create order ...
            new_order = Order(...)
            # ...
            redirect_url = f"/track/{new_order.tracking_token}?new=true"
        except Exception:
            pass # Ignore if pending booking is invalid

    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    response.delete_cookie("pending_booking")
    return response


# ... (HTML page GET endpoints are unchanged)
@router.get("/register", response_class=HTMLResponse, include_in_schema=False)
async def get_registration_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.get("/register/customer", response_class=HTMLResponse, include_in_schema=False)
async def get_customer_registration_page(request: Request):
    booking_data = None
    pending_booking_cookie = request.cookies.get("pending_booking")
    if pending_booking_cookie:
        try:
            unsigned_data = signer.unsign(pending_booking_cookie).decode('utf-8')
            booking_data = json.loads(unsigned_data)
        except Exception:
            booking_data = None
            
    return templates.TemplateResponse("register_customer.html", {
        "request": request,
        "booking_data": booking_data
    })

def get_current_customer_user(current_user: User = Depends(get_current_user)) -> User:
    # ... (this function remains unchanged)
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
    """Serves the customer account page OR returns profile JSON for mobile."""
    customer_profile = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer_profile:
        raise HTTPException(status_code=404, detail="Customer profile not found")

    if wants_json(request):
        return UserProfile(
            id=user.id, name=customer_profile.full_name, email=user.email,
            phone=customer_profile.phone_number, whatsapp=customer_profile.whatsapp_number,
            address=customer_profile.address, latitude=customer_profile.latitude,
            longitude=customer_profile.longitude, role=user.role, created_at=user.created_at
        )
    
    orders = session.exec(select(Order).where(Order.customer_id == customer_profile.id).order_by(Order.created_at.desc())).all()
    return templates.TemplateResponse("account.html", {"request": request, "customer": customer_profile, "orders": orders})

@router.post("/account/update")
def update_customer_details(
    request: Request,
    full_name: str = Form(...),
    phone_number: str = Form(...),
    address: str = Form(...),
    whatsapp_number: Optional[str] = Form(None),
    user: User = Depends(get_current_customer_user),
    session: Session = Depends(get_session)
):
    """Handles updating customer details for both web and mobile."""
    customer_profile = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer_profile: raise HTTPException(status_code=404, detail="Customer profile not found")
        
    customer_profile.full_name = full_name
    customer_profile.phone_number = phone_number
    customer_profile.address = address
    customer_profile.whatsapp_number = whatsapp_number
    session.add(customer_profile)
    session.commit()
    session.refresh(customer_profile)

    if wants_json(request):
        return UserProfile(
            id=user.id, name=customer_profile.full_name, email=user.email,
            phone=customer_profile.phone_number, whatsapp=customer_profile.whatsapp_number,
            address=customer_profile.address, latitude=customer_profile.latitude,
            longitude=customer_profile.longitude, role=user.role, created_at=user.created_at
        )
    
    return RedirectResponse(url="/account", status_code=303)

# --- NEW ENDPOINT FOR MOBILE APP ---
@router.get("/api/me/orders/active", response_model=List[Order])
def get_my_active_orders(
    user: User = Depends(get_current_customer_user),
    session: Session = Depends(get_session)
):
    """Gets all active orders for the currently authenticated customer."""
    customer_profile = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer_profile:
        return []

    active_orders = session.exec(
        select(Order)
        .where(Order.customer_id == customer_profile.id, Order.status.notin_(["Delivered", "Closed"]))
        .order_by(Order.created_at.desc())
    ).all()
    return active_orders