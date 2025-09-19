# app/routes/users.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import User, Customer, Order
from app.auth import get_password_hash, create_access_token, get_current_user
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
    
    return templates.TemplateResponse("login.html", {
        "request": request, "success": "Registration successful! Please wait for an admin to approve your account."
    })


@router.post("/register/customer", include_in_schema=False)
async def handle_customer_registration(
    request: Request,
    response: Response,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    phone_number: str = Form(...),
    address: str = Form(...),
    session: Session = Depends(get_session)
):
    """Endpoint for customers to register. They are active immediately and logged in."""
    existing_user = session.exec(select(User).where(User.email == email)).first()
    if existing_user:
        return templates.TemplateResponse("register_customer.html", {
            "request": request, "error": "Email is already registered."
        }, status_code=409)

    hashed_password = get_password_hash(password)
    
    # Create the authentication user
    new_user = User(
        username=email, # Use email as username for customers
        email=email,
        hashed_password=hashed_password,
        display_name=full_name,
        role="customer",
        is_active=True # Customers are active by default
    )
    session.add(new_user)
    session.commit()
    session.refresh(new_user)

    # Create the linked customer profile
    new_customer_profile = Customer(
        user_id=new_user.id,
        full_name=full_name,
        phone_number=phone_number,
        address=address
    )
    session.add(new_customer_profile)
    session.commit()
    
    # Log the user in immediately
    access_token = create_access_token(data={"sub": new_user.username})
    response = RedirectResponse(url="/book", status_code=303)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response


# HTML Pages for Registration
@router.get("/register", response_class=HTMLResponse, include_in_schema=False)
async def get_registration_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.get("/register/customer", response_class=HTMLResponse, include_in_schema=False)
async def get_customer_registration_page(request: Request):
    return templates.TemplateResponse("register_customer.html", {"request": request})

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