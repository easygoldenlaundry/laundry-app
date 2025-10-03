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
from app.auth import get_password_hash, create_access_token, get_current_user, get_current_customer_user
from app.security import signer
from app.sockets import broadcast_order_update
from starlette.responses import Response

# Router for HTML-serving web pages
router = APIRouter()
# Router for JSON-serving mobile API
api_router = APIRouter(prefix="/api", tags=["Mobile Customer API"])

templates = Jinja2Templates(directory="app/templates")

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

# --- NEW: Mobile App API Endpoints (JSON only) ---

@api_router.post("/customers/register", response_model=TokenResponse)
async def register_customer_api(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    phone_number: str = Form(...),
    address: str = Form(...),
    whatsapp_number: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    """Handles customer registration for the mobile app, always returning JSON."""
    existing_user = session.exec(select(User).where(User.email == email)).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Email is already registered")

    hashed_password = get_password_hash(password)
    new_user = User(
        username=email, email=email, hashed_password=hashed_password,
        display_name=full_name, role="customer", is_active=True
    )
    session.add(new_user)
    session.commit(); session.refresh(new_user)

    new_customer = Customer(
        user_id=new_user.id, full_name=full_name, phone_number=phone_number,
        address=address, whatsapp_number=whatsapp_number
    )
    session.add(new_customer)
    session.commit(); session.refresh(new_customer)
    
    access_token = create_access_token(data={"sub": new_user.username})
    user_profile = UserProfile(
        id=new_user.id, name=new_customer.full_name, email=new_user.email,
        phone=new_customer.phone_number, whatsapp=new_customer.whatsapp_number,
        address=new_customer.address, latitude=new_customer.latitude, longitude=new_customer.longitude,
        role=new_user.role, created_at=new_user.created_at
    )
    return TokenResponse(access_token=access_token, user=user_profile)

@api_router.get("/me", response_model=UserProfile)
def get_current_user_profile(
    user: User = Depends(get_current_customer_user),
    session: Session = Depends(get_session)
):
    """Gets the profile for the currently authenticated user."""
    customer = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    
    return UserProfile(
        id=user.id, name=customer.full_name, email=user.email,
        phone=customer.phone_number, whatsapp=customer.whatsapp_number,
        address=customer.address, latitude=customer.latitude,
        longitude=customer.longitude, role=user.role, created_at=user.created_at
    )

@api_router.post("/me/update", response_model=UserProfile)
def update_current_user_profile(
    full_name: str = Form(...),
    phone_number: str = Form(...),
    address: str = Form(...),
    whatsapp_number: Optional[str] = Form(None),
    user: User = Depends(get_current_customer_user),
    session: Session = Depends(get_session)
):
    """Updates the profile for the currently authenticated user."""
    customer = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found")

    customer.full_name = full_name
    customer.phone_number = phone_number
    customer.address = address
    customer.whatsapp_number = whatsapp_number
    session.add(customer)
    session.commit()
    session.refresh(customer)

    return UserProfile(
        id=user.id, name=customer.full_name, email=user.email,
        phone=customer.phone_number, whatsapp=customer.whatsapp_number,
        address=customer.address, latitude=customer.latitude,
        longitude=customer.longitude, role=user.role, created_at=user.created_at
    )

@api_router.get("/me/orders/active", response_model=List[Order])
def get_my_active_orders(
    user: User = Depends(get_current_customer_user),
    session: Session = Depends(get_session)
):
    """Gets all active orders for the currently authenticated customer."""
    customer_profile = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer_profile: return []

    active_orders = session.exec(
        select(Order)
        .where(Order.customer_id == customer_profile.id, Order.status.notin_(["Delivered", "Closed"]))
        .order_by(Order.created_at.desc())
    ).all()
    return active_orders


# --- Existing Web Endpoints (HTML only) ---

@router.post("/register", include_in_schema=False)
async def handle_staff_registration(
    request: Request, username: str = Form(...), email: str = Form(...),
    password: str = Form(...), display_name: str = Form(...), role: str = Form(...),
    session: Session = Depends(get_session)
):
    existing_user = session.exec(select(User).where((User.username == username) | (User.email == email))).first()
    if existing_user:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Username or email already registered."}, status_code=409)

    new_user = User(
        username=username, email=email, hashed_password=get_password_hash(password),
        display_name=display_name, role=role, is_active=False
    )
    session.add(new_user)
    session.commit()
    
    return templates.TemplateResponse("login.html", {"request": request, "success": "Registration successful! Please wait for an admin to approve your account.", "prefill_username": username})

@router.post("/register/customer", include_in_schema=False)
async def handle_customer_registration_web(
    request: Request, full_name: str = Form(...), email: str = Form(...), password: str = Form(...),
    phone_number: str = Form(...), address: str = Form(...), whatsapp_number: Optional[str] = Form(None),
    pending_booking: Optional[str] = Form(None), session: Session = Depends(get_session)
):
    """Endpoint for web customers to register. They are active immediately and logged in."""
    existing_user = session.exec(select(User).where(User.email == email)).first()
    if existing_user:
        return templates.TemplateResponse("register_customer.html", {"request": request, "error": "Email is already registered."}, status_code=409)

    new_user = User(username=email, email=email, hashed_password=get_password_hash(password), display_name=full_name, role="customer", is_active=True)
    session.add(new_user)
    session.commit(); session.refresh(new_user)

    new_customer = Customer(user_id=new_user.id, full_name=full_name, phone_number=phone_number, address=address, whatsapp_number=whatsapp_number)
    session.add(new_customer)
    session.commit(); session.refresh(new_customer)
    
    redirect_url = "/account"

    if pending_booking:
        try:
            unsigned_data = signer.unsign(pending_booking).decode('utf-8')
            booking_data = json.loads(unsigned_data)
            # (Logic to create order from pending booking data)
            # ...
        except Exception as e:
            print(f"Error processing pending booking after registration: {e}")
    
    access_token = create_access_token(data={"sub": new_user.username})
    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    response.delete_cookie("pending_booking")
    return response

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
    return templates.TemplateResponse("register_customer.html", {"request": request, "booking_data": booking_data})

@router.get("/account", response_class=HTMLResponse)
def get_customer_account_page(request: Request, user: User = Depends(get_current_customer_user), session: Session = Depends(get_session)):
    customer = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer: raise HTTPException(status_code=404, detail="Customer profile not found")
    orders = session.exec(select(Order).where(Order.customer_id == customer.id).order_by(Order.created_at.desc())).all()
    return templates.TemplateResponse("account.html", {"request": request, "customer": customer, "orders": orders})

@router.post("/account/update")
def update_customer_details_web(
    request: Request, full_name: str = Form(...), phone_number: str = Form(...), address: str = Form(...),
    whatsapp_number: Optional[str] = Form(None), user: User = Depends(get_current_customer_user), session: Session = Depends(get_session)
):
    customer = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer: raise HTTPException(status_code=404, detail="Customer profile not found")
        
    customer.full_name = full_name
    customer.phone_number = phone_number
    customer.address = address
    customer.whatsapp_number = whatsapp_number
    session.add(customer)
    session.commit()
    return RedirectResponse(url="/account", status_code=303)