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
from app.models import User, Customer, Order, Bag, Setting, Event, Driver, FinanceEntry
from app.auth import get_password_hash, create_access_token, get_current_user, get_current_api_user, get_current_customer_user
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
    staysoft_preference: Optional[str]
    additional_notes: Optional[str]
    role: str
    created_at: Optional[datetime]

# --- NEW: Simplified Public User model ---
class UserPublic(BaseModel):
    id: int
    display_name: str
    role: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile

class CustomerRegistrationRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    phone_number: str
    address: str
    whatsapp_number: Optional[str] = None
    staysoft_preference: Optional[str] = None
    additional_notes: Optional[str] = None

class ProfileUpdateRequest(BaseModel):
    full_name: str
    phone_number: str
    address: str
    whatsapp_number: Optional[str] = None
    staysoft_preference: Optional[str] = None
    additional_notes: Optional[str] = None


# --- NEW: Mobile App API Endpoints (JSON only) ---

# --- NEW ENDPOINT ---
@api_router.get("/users/{user_id}", response_model=UserPublic)
def get_user_public_profile(
    user_id: int,
    user: User = Depends(get_current_api_user),
    session: Session = Depends(get_session)
):
    """Gets basic, public-safe information for any user by their ID."""
    target_user = session.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserPublic.from_orm(target_user)


@api_router.post("/customers/register", response_model=TokenResponse)
async def register_customer_api(
    request_data: CustomerRegistrationRequest,
    session: Session = Depends(get_session)
):
    # ... (rest of the file is unchanged) ...
    existing_user = session.exec(select(User).where(User.email == request_data.email)).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Email is already registered")

    hashed_password = get_password_hash(request_data.password)
    new_user = User(
        username=request_data.email, email=request_data.email, hashed_password=hashed_password,
        display_name=request_data.full_name, role="customer", is_active=True
    )
    session.add(new_user)
    session.commit(); session.refresh(new_user)

    new_customer = Customer(
        user_id=new_user.id, full_name=request_data.full_name, phone_number=request_data.phone_number,
        address=request_data.address, whatsapp_number=request_data.whatsapp_number,
        staysoft_preference=request_data.staysoft_preference, additional_notes=request_data.additional_notes
    )
    session.add(new_customer)
    session.commit(); session.refresh(new_customer)
    
    access_token = create_access_token(data={"sub": new_user.username})
    user_profile = UserProfile(
        id=new_user.id, name=new_customer.full_name, email=new_user.email,
        phone=new_customer.phone_number, whatsapp=new_customer.whatsapp_number,
        address=new_customer.address, latitude=new_customer.latitude, longitude=new_customer.longitude,
        staysoft_preference=new_customer.staysoft_preference, additional_notes=new_customer.additional_notes,
        role=new_user.role, created_at=new_user.created_at
    )
    return TokenResponse(access_token=access_token, user=user_profile)

@api_router.get("/me", response_model=UserProfile)
def get_current_user_profile(
    user: User = Depends(get_current_api_user),
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
        longitude=customer.longitude, staysoft_preference=customer.staysoft_preference,
        additional_notes=customer.additional_notes, role=user.role, created_at=user.created_at
    )

@api_router.post("/me/update", response_model=UserProfile)
def update_current_user_profile(
    request_data: ProfileUpdateRequest,
    user: User = Depends(get_current_api_user),
    session: Session = Depends(get_session)
):
    """Updates the profile for the currently authenticated user."""
    customer = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found")

    customer.full_name = request_data.full_name
    customer.phone_number = request_data.phone_number
    customer.address = request_data.address
    customer.whatsapp_number = request_data.whatsapp_number
    customer.staysoft_preference = request_data.staysoft_preference
    customer.additional_notes = request_data.additional_notes
    session.add(customer)
    session.commit()
    session.refresh(customer)

    return UserProfile(
        id=user.id, name=customer.full_name, email=user.email,
        phone=customer.phone_number, whatsapp=customer.whatsapp_number,
        address=customer.address, latitude=customer.latitude,
        longitude=customer.longitude, staysoft_preference=customer.staysoft_preference,
        additional_notes=customer.additional_notes, role=user.role, created_at=user.created_at
    )

@api_router.get("/me/orders/active", response_model=List[Order])
def get_my_active_orders(
    user: User = Depends(get_current_api_user),
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

@api_router.delete("/me/delete-account")
def delete_account_api(
    user: User = Depends(get_current_api_user),
    session: Session = Depends(get_session)
):
    """
    Deletes the currently authenticated user's account and all personal data.
    
    This endpoint:
    1. Immediately deactivates the account
    2. Deletes personal information from User and Customer tables
    3. Anonymizes order data (removes customer link but keeps orders for legal/accounting)
    4. Returns success confirmation
    
    WARNING: This action is permanent and cannot be undone!
    """
    # Only allow customers to delete their own accounts
    if user.role != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Only customer accounts can be deleted through this endpoint"
        )
    
    try:
        # Get customer profile
        customer_profile = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
        
        # Anonymize all orders (keep for legal/accounting but remove personal data)
        if customer_profile:
            orders = session.exec(select(Order).where(Order.customer_id == customer_profile.id)).all()
            for order in orders:
                order.customer_name = "DELETED USER"
                order.customer_phone = "DELETED"
                order.customer_address = "DELETED"
                order.customer_id = None  # Remove link to customer
                order.notes_for_driver = None  # Remove any personal notes
                session.add(order)
            
            # Delete customer profile
            session.delete(customer_profile)
        
        # Delete user account
        session.delete(user)
        
        # Commit all changes
        session.commit()
        
        return {
            "success": True,
            "message": "Your account has been permanently deleted. All personal data has been removed."
        }
        
    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete account: {str(e)}"
        )


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
    session.refresh(new_user)
    
    # Create Driver profile if registering as a driver
    if role == "driver":
        driver_profile = Driver(user_id=new_user.id, status="idle")
        session.add(driver_profile)
        session.commit()
    
    return templates.TemplateResponse("login.html", {"request": request, "success": "Registration successful! Please wait for an admin to approve your account.", "prefill_username": username})

@router.post("/register/customer", include_in_schema=False)
async def handle_customer_registration_web(
    request: Request, full_name: str = Form(...), email: str = Form(...), password: str = Form(...),
    phone_number: str = Form(...), address: str = Form(...), whatsapp_number: Optional[str] = Form(None),
    staysoft_preference: Optional[str] = Form(None), additional_notes: Optional[str] = Form(None),
    pending_booking: Optional[str] = Form(None), session: Session = Depends(get_session)
):
    """Endpoint for web customers to register. They are active immediately and logged in."""
    existing_user = session.exec(select(User).where(User.email == email)).first()
    if existing_user:
        return templates.TemplateResponse("register_customer.html", {"request": request, "error": "Email is already registered."}, status_code=409)

    new_user = User(username=email, email=email, hashed_password=get_password_hash(password), display_name=full_name, role="customer", is_active=True)
    session.add(new_user)
    session.commit(); session.refresh(new_user)

    new_customer = Customer(user_id=new_user.id, full_name=full_name, phone_number=phone_number, address=address, whatsapp_number=whatsapp_number, staysoft_preference=staysoft_preference, additional_notes=additional_notes)
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
def get_customer_account_page(
    request: Request,
    tab: str = "active",
    sort: str = "default",
    user: User = Depends(get_current_customer_user),
    session: Session = Depends(get_session)
):
    customer = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer: raise HTTPException(status_code=404, detail="Customer profile not found")

    # Define active and completed order statuses
    active_statuses = ["Created", "PickedUp", "AssignedToDriver", "Processing", "ReadyForDelivery", "OutForDelivery"]
    completed_statuses = ["Delivered", "Closed"]

    if tab == "active":
        # Get active orders
        orders = session.exec(
            select(Order)
            .where(Order.customer_id == customer.id, Order.status.in_(active_statuses))
            .order_by(Order.created_at.desc())
        ).all()
    elif tab == "history":
        # Get completed orders with sorting
        query = select(Order).where(Order.customer_id == customer.id, Order.status.in_(completed_statuses))

        if sort == "date_newest":
            query = query.order_by(Order.delivered_at.desc())
        elif sort == "date_oldest":
            query = query.order_by(Order.delivered_at.asc())
        elif sort == "price_high":
            # We'll sort by price after calculating costs
            query = query.order_by(Order.id.desc())  # Default fallback
        elif sort == "price_low":
            # We'll sort by price after calculating costs
            query = query.order_by(Order.id.desc())  # Default fallback
        else:  # default = most recent completion
            query = query.order_by(Order.delivered_at.desc())

        orders = session.exec(query).all()
    else:
        # Default to active orders
        orders = session.exec(
            select(Order)
            .where(Order.customer_id == customer.id, Order.status.in_(active_statuses))
            .order_by(Order.created_at.desc())
        ).all()

    # Enhance orders with cost and driver info (same as API endpoint)
    enhanced_orders = []
    for order in orders:
        # Calculate total cost from finance entries
        total_cost = 0.0
        finance_entries = session.exec(
            select(FinanceEntry)
            .where(FinanceEntry.order_id == order.id, FinanceEntry.entry_type == 'revenue')
        ).all()
        for entry in finance_entries:
            total_cost += entry.amount

        # Get driver info if assigned
        driver_name = None
        driver_id = None
        if order.assigned_driver_id:
            driver = session.exec(select(Driver).where(Driver.id == order.assigned_driver_id)).first()
            if driver:
                driver_user = session.get(User, driver.user_id)
                if driver_user:
                    driver_name = driver_user.display_name
                    driver_id = driver.id

        # Use confirmed_load_count if available, otherwise basket_count, otherwise 0
        number_of_loads = order.confirmed_load_count or order.basket_count or 0
        
        # Get price_per_load based on processing_option
        price_per_load = None
        try:
            if order.processing_option == "wait_and_save":
                price_setting = session.get(Setting, "wait_and_save_price_per_load")
                price_per_load = float(price_setting.value) if price_setting else 150.0
            else:  # standard or None defaults to standard
                price_setting = session.get(Setting, "standard_price_per_load")
                price_per_load = float(price_setting.value) if price_setting else 210.0
        except Exception:
            # Fallback if settings not available
            price_per_load = 210.0 if not order.processing_option or order.processing_option == "standard" else 150.0

        # Calculate fulfillment time for completed orders
        fulfillment_time = None
        if order.delivered_at and order.created_at:
            duration = order.delivered_at - order.created_at
            hours = duration.total_seconds() // 3600
            minutes = (duration.total_seconds() % 3600) // 60
            if hours > 0:
                fulfillment_time = f"{int(hours)} hours, {int(minutes)} minutes"
            else:
                fulfillment_time = f"{int(minutes)} minutes"

        # Create enhanced order object
        enhanced_order = {
            'id': order.id,
            'external_id': order.external_id,
            'tracking_token': order.tracking_token,
            'customer_name': order.customer_name,
            'customer_phone': order.customer_phone,
            'customer_address': order.customer_address,
            'hub_id': order.hub_id,
            'status': order.status,
            'total_items': order.total_items,
            'sla_deadline': order.sla_deadline,
            'assigned_driver_id': order.assigned_driver_id,
            'pickup_pin': order.pickup_pin,
            'delivery_pin': order.delivery_pin,
            'basket_count': order.basket_count,
            'created_at': order.created_at,
            'updated_at': order.updated_at,
            'customer_id': order.customer_id,
            'confirmed_load_count': order.confirmed_load_count,
            'dispatch_method': order.dispatch_method,
            'distance_km': order.distance_km,
            'pickup_cost': order.pickup_cost,
            'delivery_cost': getattr(order, 'delivery_cost', None),
            'delivery_distance_km': getattr(order, 'delivery_distance_km', None),
            'pickup_lat': order.pickup_lat,
            'pickup_lon': order.pickup_lon,
            'delivery_lat': order.delivery_lat,
            'delivery_lon': order.delivery_lon,
            'initial_driver_lat': order.initial_driver_lat,
            'initial_driver_lon': order.initial_driver_lon,
            'picked_up_at': order.picked_up_at,
            'at_hub_at': order.at_hub_at,
            'imaging_started_at': order.imaging_started_at,
            'imaging_completed_at': order.imaging_completed_at,
            'processing_started_at': order.processing_started_at,
            'qa_started_at': order.qa_started_at,
            'ready_for_delivery_at': order.ready_for_delivery_at,
            'out_for_delivery_at': order.out_for_delivery_at,
            'delivered_at': order.delivered_at,
            'closed_at': order.closed_at,
            'imaged_items_count': order.imaged_items_count,
            # Enhanced fields
            'total_cost': total_cost,
            'number_of_loads': number_of_loads,
            'price_per_load': price_per_load,
            'driver_name': driver_name,
            'driver_id': driver_id,
            'fulfillment_time': fulfillment_time
        }
        enhanced_orders.append(enhanced_order)

    # For history tab with price sorting, sort the enhanced orders by total_cost
    if tab == "history" and sort in ["price_high", "price_low"]:
        if sort == "price_high":
            enhanced_orders.sort(key=lambda x: x['total_cost'], reverse=True)
        elif sort == "price_low":
            enhanced_orders.sort(key=lambda x: x['total_cost'])

    return templates.TemplateResponse("account.html", {
        "request": request,
        "customer": customer,
        "orders": enhanced_orders,
        "current_tab": tab,
        "current_sort": sort
    })

@router.post("/account/update")
def update_customer_details_web(
    request: Request, full_name: str = Form(...), phone_number: str = Form(...), address: str = Form(...),
    whatsapp_number: Optional[str] = Form(None), staysoft_preference: Optional[str] = Form(None), 
    additional_notes: Optional[str] = Form(None), user: User = Depends(get_current_customer_user), session: Session = Depends(get_session)
):
    customer = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer: raise HTTPException(status_code=404, detail="Customer profile not found")
        
    customer.full_name = full_name
    customer.phone_number = phone_number
    customer.address = address
    customer.whatsapp_number = whatsapp_number
    customer.staysoft_preference = staysoft_preference
    customer.additional_notes = additional_notes
    session.add(customer)
    session.commit()
    return RedirectResponse(url="/account", status_code=303)

@router.post("/account/delete")
def delete_account_web(
    request: Request,
    user: User = Depends(get_current_customer_user),
    session: Session = Depends(get_session)
):
    """
    Web endpoint to delete customer account.
    Redirects to login page after successful deletion.
    """
    # Only allow customers to delete their own accounts
    if user.role != "customer":
        raise HTTPException(status_code=403, detail="Only customer accounts can be deleted")
    
    try:
        # Get customer profile
        customer_profile = session.exec(select(Customer).where(Customer.user_id == user.id)).first()

        # Anonymize all orders first (keep for legal/accounting but remove personal data)
        if customer_profile:
            orders = session.exec(select(Order).where(Order.customer_id == customer_profile.id)).all()
            for order in orders:
                order.customer_name = "DELETED USER"
                order.customer_phone = "DELETED"
                order.customer_address = "DELETED"
                order.customer_id = None  # Remove link to customer
                order.notes_for_driver = None
                session.add(order)

            # Delete customer profile
            session.delete(customer_profile)

        # Delete user account last (after removing all references)
        session.delete(user)

        # Commit all changes in a single transaction
        session.commit()

        # Redirect to login page with success message
        response = RedirectResponse(url="/login?message=Account+successfully+deleted", status_code=303)
        response.delete_cookie("access_token")
        return response
        
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete account: {str(e)}")

@router.get("/delete-account-info", response_class=HTMLResponse, include_in_schema=False)
async def delete_account_info_page(request: Request):
    """Public page explaining account deletion policy (for Google Play Store)"""
    return templates.TemplateResponse("delete_account.html", {"request": request})