# app/routes/orders.py
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File, Request, Body
from sqlmodel import Session, select, delete, update
from typing import List, Optional, Union
from pydantic import BaseModel, Field
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone

from app.db import get_session
from app.models import Order, Bag, Image, Item, Basket, User, Message, Customer, Driver, FinanceEntry, Setting, Review
from app.services.state_machine import apply_transition
from app.auth import get_current_admin_user, get_current_api_user # Use the working admin auth
from app.sockets import broadcast_message_update, broadcast_admin_notification, broadcast_order_update
from app.config import DATA_ROOT
import aiofiles
import os

router = APIRouter(prefix="/api/orders", tags=["Orders"])

class OrderResponse(BaseModel):
    id: int
    customer_id: int
    status: str
    total_cost: float
    number_of_loads: int
    created_at: datetime
    driver_name: Optional[str] = None
    driver_id: Optional[int] = None
    processing_option: Optional[str] = None  # "standard" or "wait_and_save"
    price_per_load: Optional[float] = None
    pickup_cost: Optional[float] = None
    delivery_cost: Optional[float] = None
    # Review fields
    has_review: bool = False
    pickup_delivery_rating: Optional[int] = None
    laundry_quality_rating: Optional[int] = None
    feedback_text: Optional[str] = None
    reviewed_at: Optional[datetime] = None

# --- NEW ENDPOINT: Get all orders for authenticated user ---
@router.get("/my-orders", response_model=List[OrderResponse])
def get_my_orders(
    user: User = Depends(get_current_api_user),
    session: Session = Depends(get_session)
):
    """
    Gets all orders for the currently authenticated customer.
    Returns orders in descending chronological order (newest first).
    """
    # Get customer profile for the authenticated user
    customer_profile = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer_profile:
        return []

    # Get all orders for this customer
    orders = session.exec(
        select(Order)
        .where(Order.customer_id == customer_profile.id)
        .order_by(Order.created_at.desc())
    ).all()

    response_orders = []
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

        # Get review data if exists
        review = session.exec(select(Review).where(Review.order_id == order.id)).first()
        has_review = review is not None
        pickup_delivery_rating = review.pickup_delivery_rating if review else None
        laundry_quality_rating = review.laundry_quality_rating if review else None
        feedback_text = review.feedback_text if review else None
        reviewed_at = review.created_at if review else None

        response_orders.append(OrderResponse(
            id=order.id,
            customer_id=order.customer_id,
            status=order.status,
            total_cost=total_cost,
            number_of_loads=number_of_loads,
            created_at=order.created_at,
            driver_name=driver_name,
            driver_id=driver_id,
            processing_option=order.processing_option,
            price_per_load=price_per_load,
            pickup_cost=order.pickup_cost,
            delivery_cost=getattr(order, 'delivery_cost', None),
            has_review=has_review,
            pickup_delivery_rating=pickup_delivery_rating,
            laundry_quality_rating=laundry_quality_rating,
            feedback_text=feedback_text,
            reviewed_at=reviewed_at
        ))

    return response_orders

# --- NEW Pydantic Models for Response ---
class DriverPublic(BaseModel):
    id: int
    display_name: str

class OrderWithDriverResponse(BaseModel):
    order: Order
    driver: Optional[DriverPublic] = None


class ImageCompletionRequest(BaseModel):
    user_id: int
    basket_count: int

class DeliveryRequest(BaseModel):
    delivery_address: str
    delivery_latitude: float
    delivery_longitude: float
    phone: str
    delivery_cost: Optional[float] = None
    distance_km: Optional[float] = None

class MessagePublic(BaseModel):
    id: int
    order_id: int
    sender_id: int
    sender_name: str
    sender_role: str
    message: str
    timestamp: datetime
    read: bool

# --- NEW ENDPOINT ---
@router.get("/{order_id}", response_model=OrderWithDriverResponse)
def get_order_details(
    order_id: int,
    user: User = Depends(get_current_api_user),
    session: Session = Depends(get_session)
):
    """
    Gets the full details for a single order, including driver info.
    Protected to ensure only the customer or an admin can access it.
    """
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Security check: User must be an admin or the customer who owns the order
    if user.role != "admin" and order.customer_id != user.id:
        customer = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
        if not customer or customer.id != order.customer_id:
            raise HTTPException(status_code=403, detail="Not authorized to view this order")

    driver_info = None
    if order.assigned_driver_id:
        # Get the driver record first, then get the user info
        driver = session.exec(select(Driver).where(Driver.id == order.assigned_driver_id)).first()
        if driver:
            driver_user = session.get(User, driver.user_id)
            if driver_user:
                driver_info = DriverPublic(id=driver.id, display_name=driver_user.display_name)
    
    return OrderWithDriverResponse(order=order, driver=driver_info)

@router.get("/{order_id}/bag", response_model=Bag)
def get_order_bag(order_id: int, session: Session = Depends(get_session)):
    statement = select(Bag).where(Bag.order_id == order_id)
    bag = session.exec(statement).first()
    if not bag:
        raise HTTPException(status_code=404, detail="Bag not found for this order")
    return bag

@router.post("/{order_id}/upload-image")
async def upload_order_image(
    order_id: int,
    bag_id: int = Form(...),
    item_index: int = Form(...),
    user_id: int = Form(...),
    is_stain: bool = Form(...),
    proof_photo: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    new_item = Item(
        order_id=order_id,
        bag_id=bag_id,
        name=f"Item #{item_index}",
        imaged=True,
        stain_flags="stain_detected" if is_stain else None
    )
    session.add(new_item)
    session.commit()
    session.refresh(new_item)

    upload_dir = os.path.join(DATA_ROOT, "images", str(order_id))
    os.makedirs(upload_dir, exist_ok=True)
    filename = f"item_{new_item.id}_{proof_photo.filename}"
    file_path_on_disk = os.path.join(upload_dir, filename)

    async with aiofiles.open(file_path_on_disk, 'wb') as out_file:
        content = await proof_photo.read()
        await out_file.write(content)

    relative_path_for_web = os.path.join("data", "images", str(order_id), filename).replace("\\", "/")

    db_image = Image(
        order_id=order_id,
        bag_id=bag_id,
        item_id=new_item.id,
        path=relative_path_for_web,
        image_type="item_scan",
        uploaded_by=user_id,
        is_stain=is_stain
    )
    session.add(db_image)
    session.commit()
    session.refresh(db_image)
    
    return {"filename": filename, "image_id": db_image.id, "item_id": new_item.id}


@router.post("/{order_id}/complete-imaging", response_model=Order)
def complete_imaging_stage(order_id: int, request: ImageCompletionRequest, session: Session = Depends(get_session)):
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    items_in_order = session.exec(select(Item).where(Item.order_id == order_id)).all()
    if not items_in_order:
        raise HTTPException(status_code=400, detail="Cannot complete imaging with 0 items scanned.")
    
    order.total_items = len(items_in_order)
    order.imaged_items_count = len(items_in_order)
    order.imaging_completed_at = datetime.now(timezone.utc)
    order.basket_count = request.basket_count
    
    session.exec(delete(Basket).where(Basket.order_id == order_id))
    session.commit()

    for i in range(request.basket_count):
        basket = Basket(
            order_id=order.id,
            basket_index=i + 1,
            status="Pretreat" 
        )
        session.add(basket)

    updated_order = apply_transition(session, order, "Processing", user_id=request.user_id)
    return updated_order

@router.post("/{order_id}/request-delivery", response_model=Order)
def request_delivery(order_id: int, delivery_request: Optional[DeliveryRequest] = Body(default=None), session: Session = Depends(get_session)):
    """
    Customer-triggered action to set delivery details and move an order to 'OutForDelivery'.
    If no delivery_request is provided, uses customer's existing delivery information.
    """
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "ReadyForDelivery":
        raise HTTPException(status_code=400, detail="Order is not ready for delivery request.")

    # Get customer information
    if not order.customer_id:
        raise HTTPException(status_code=400, detail=f"Order {order_id} has no associated customer")

    customer = session.get(Customer, order.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer with ID {order.customer_id} not found for order {order_id}")

    # Use provided delivery data or fall back to customer's existing data
    if delivery_request:
        delivery_address = delivery_request.delivery_address
        delivery_latitude = delivery_request.delivery_latitude
        delivery_longitude = delivery_request.delivery_longitude
        phone = delivery_request.phone

        # Update order with delivery cost and distance (if fields exist in schema)
        try:
            if delivery_request.delivery_cost is not None and hasattr(order, 'delivery_cost'):
                order.delivery_cost = delivery_request.delivery_cost
            if delivery_request.distance_km is not None and hasattr(order, 'delivery_distance_km'):
                order.delivery_distance_km = delivery_request.distance_km
        except Exception:
            pass  # Gracefully handle if new fields don't exist yet

        # Update customer profile with new delivery details
        customer.address = delivery_address
        customer.latitude = delivery_latitude
        customer.longitude = delivery_longitude
        customer.phone_number = phone
        session.add(customer)
    else:
        # Use order's delivery information first, then fall back to customer's profile
        if hasattr(order, 'delivery_lat') and order.delivery_lat and hasattr(order, 'delivery_lon') and order.delivery_lon and order.customer_address and order.customer_phone:
            # Use delivery info already stored on the order
            delivery_address = order.customer_address
            delivery_latitude = order.delivery_lat
            delivery_longitude = order.delivery_lon
            phone = order.customer_phone
        elif customer.latitude and customer.longitude and customer.address and customer.phone_number:
            # Fall back to customer's profile
            delivery_address = customer.address
            delivery_latitude = customer.latitude
            delivery_longitude = customer.longitude
            phone = customer.phone_number
        else:
            raise HTTPException(status_code=400, detail="Delivery information is incomplete. Please ensure the order or customer profile contains delivery address, coordinates, and phone number.")

    # Update delivery location on order
    order.delivery_lat = delivery_latitude
    order.delivery_lon = delivery_longitude
    order.customer_address = delivery_address
    order.customer_phone = phone
    session.add(order)

    updated_order = apply_transition(session, order, "OutForDelivery", meta={"customer_triggered": True})
    return updated_order

class ReviewRequest(BaseModel):
    pickup_delivery_rating: int = Field(..., ge=1, le=5, description="Rating 1-5 for pickup/delivery service")
    laundry_quality_rating: int = Field(..., ge=1, le=5, description="Rating 1-5 for laundry quality")
    feedback_text: Optional[str] = Field(None, max_length=500, description="Optional feedback")

@router.post("/{order_id}/submit-review")
def submit_review(
    order_id: int,
    review_data: ReviewRequest,
    user: User = Depends(get_current_api_user),
    session: Session = Depends(get_session)
):
    """Submit customer ratings and feedback for a completed order."""
    # Get customer profile for the authenticated user
    customer = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found")
    
    # Verify order exists and belongs to user
    order = session.exec(
        select(Order)
        .where(Order.id == order_id, Order.customer_id == customer.id)
    ).first()
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Verify order is completed (Delivered or Closed)
    if order.status not in ["Delivered", "Closed"]:
        raise HTTPException(
            status_code=400, 
            detail="Can only review completed orders (status must be Delivered or Closed)"
        )
    
    # Check if review already exists
    existing_review = session.exec(
        select(Review).where(Review.order_id == order_id)
    ).first()
    
    if existing_review:
        raise HTTPException(
            status_code=409, 
            detail="Review already submitted for this order"
        )
    
    # Create review
    new_review = Review(
        order_id=order_id,
        customer_id=customer.id,
        pickup_delivery_rating=review_data.pickup_delivery_rating,
        laundry_quality_rating=review_data.laundry_quality_rating,
        feedback_text=review_data.feedback_text,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    
    session.add(new_review)
    session.commit()
    session.refresh(new_review)
    
    return {
        "message": "Thank you for your feedback!",
        "review_id": new_review.id,
        "order_id": order_id
    }

@router.get("/{order_id}/stained-images", response_model=List[Image])
def get_stained_images(order_id: int, session: Session = Depends(get_session)):
    images = session.exec(
        select(Image).where(Image.order_id == order_id, Image.is_stain == True)
    ).all()
    return images


class QAImageUpdateRequest(BaseModel):
    qa_status: str
    qa_notes: Optional[str] = None

@router.post("/images/{image_id}/qa-update", response_model=Image)
def update_image_qa_status(image_id: int, request: QAImageUpdateRequest, session: Session = Depends(get_session)):
    image = session.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    image.qa_status = request.qa_status
    image.qa_notes = request.qa_notes
    session.add(image)
    session.commit()
    session.refresh(image)
    return image

@router.get("/{order_id}/messages", response_model=List[MessagePublic])
def get_messages(order_id: int, session: Session = Depends(get_session)):
    """Fetches the chat history for an order, enriched for mobile app response."""
    order = session.get(Order, order_id)
    if not order: raise HTTPException(404, "Order not found")

    messages_db = session.exec(
        select(Message).where(Message.order_id == order_id).order_by(Message.timestamp.asc())
    ).all()
    
    response = []
    for msg in messages_db:
        sender_name = "Support"
        sender_id = 0 # Placeholder for admin
        if msg.sender_role == 'customer':
            sender_name = order.customer_name
            sender_id = order.customer.user_id if order.customer else -1
        
        response.append(MessagePublic(
            id=msg.id, order_id=msg.order_id, sender_id=sender_id,
            sender_name=sender_name, sender_role=msg.sender_role,
            message=msg.content, timestamp=msg.timestamp, read=msg.is_read
        ))
    return response

class MessageCreate(BaseModel):
    message: str

@router.post("/{order_id}/messages", response_model=MessagePublic)
async def send_message(
    order_id: int,
    message_data: MessageCreate,
    request: Request,
    session: Session = Depends(get_session)
):
    order = session.get(Order, order_id)
    if not order: raise HTTPException(404, "Order not found")
    
    # Get user from request state (web interface) or try API auth
    user = getattr(request.state, "user", None)
    if not user:
        # Try API authentication as fallback
        try:
            from app.auth import get_current_api_user
            user = get_current_api_user(request, session)
        except:
            raise HTTPException(status_code=401, detail="Authentication required")
    
    sender_role = "unknown"
    if user.role in ["admin", "staff"]: sender_role = "admin"
    elif user.role == "customer": sender_role = "customer"
    
    if sender_role == "unknown":
         raise HTTPException(status_code=403, detail="User role not permitted to chat.")

    new_message = Message(
        order_id=order_id, content=message_data.message, sender_role=sender_role
    )
    session.add(new_message)
    session.commit()
    session.refresh(new_message)

    sender_name = user.display_name if sender_role == "customer" else "Support"
    message_dict = {
        "id": new_message.id, "order_id": new_message.order_id,
        "sender_id": user.id, "sender_name": sender_name,
        "sender_role": new_message.sender_role, "message": new_message.content,
        "timestamp": new_message.timestamp.isoformat(), "read": new_message.is_read
    }

    socket_msg = { 
        "order_id": new_message.order_id, 
        "sender_role": new_message.sender_role, 
        "message": new_message.content,  # Use 'message' to match API response
        "sender_name": sender_name,  # Add sender name for display
        "timestamp": new_message.timestamp.isoformat() 
    }
    await broadcast_message_update(socket_msg)
    
    if sender_role == "customer":
        await broadcast_admin_notification("new_customer_message")
    
    return MessagePublic(**message_dict)

@router.post("/{order_id}/messages/mark-read", status_code=204)
def mark_messages_as_read(
    order_id: int,
    request: Request,
    session: Session = Depends(get_session)
):
    # Get user from request state (web interface) or try API auth
    user = getattr(request.state, "user", None)
    if not user:
        # Try API authentication as fallback
        try:
            from app.auth import get_current_api_user
            user = get_current_api_user(request, session)
        except:
            raise HTTPException(status_code=401, detail="Authentication required")
    
    if user.role == "customer":
        sender_to_mark = 'admin'
    elif user.role in ["admin", "staff"]:
        sender_to_mark = 'customer'
    else:
        return

    statement = (
        update(Message)
        .where(
            Message.order_id == order_id,
            Message.sender_role == sender_to_mark,
            Message.is_read == False
        )
        .values(is_read=True)
    )
    session.exec(statement)
    session.commit()
    return

@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel_order(
    order_id: int,
    user: User = Depends(get_current_api_user),
    session: Session = Depends(get_session)
):
    """
    Cancels an order. Only the customer who owns the order or an admin can cancel it.
    Orders can only be cancelled if they haven't been picked up yet.
    """
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Security check: User must be an admin or the customer who owns the order
    if user.role != "admin":
        customer = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
        if not customer or customer.id != order.customer_id:
            raise HTTPException(status_code=403, detail="Not authorized to cancel this order")

    # Business logic: Only allow cancellation if order hasn't been picked up
    if order.status in ["PickedUp", "AssignedToDriver", "Processing", "ReadyForDelivery", "OutForDelivery", "Delivered", "Closed"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot cancel order. Order status is '{order.status}'. Orders can only be cancelled before pickup."
        )

    # Update order status to cancelled
    order.status = "Cancelled"
    order.updated_at = datetime.now(timezone.utc)
    session.add(order)
    session.commit()
    session.refresh(order)

    # Create a finance entry to record the cancellation (if there were any charges)
    # This helps with accounting and refunds
    existing_revenue = session.exec(
        select(FinanceEntry)
        .where(FinanceEntry.order_id == order.id, FinanceEntry.entry_type == 'revenue')
    ).all()
    
    if existing_revenue:
        # Create a negative revenue entry to offset the original charges
        total_revenue = sum(entry.amount for entry in existing_revenue)
        if total_revenue > 0:
            cancellation_entry = FinanceEntry(
                order_id=order.id,
                entry_type='revenue',
                amount=-total_revenue,  # Negative amount to offset
                description=f"Order cancellation - refund for order #{order.external_id}",
                timestamp=datetime.now(timezone.utc)
            )
            session.add(cancellation_entry)
            session.commit()

    # Calculate total cost for response (should be 0 after cancellation)
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

    # Broadcast order update to admin dashboard
    broadcast_order_update({
        "order_id": order.id,
        "status": order.status,
        "action": "cancelled",
        "customer_id": order.customer_id
    })

    # Notify admin about the cancellation
    broadcast_admin_notification("order_cancelled")

    return OrderResponse(
        id=order.id,
        customer_id=order.customer_id,
        status=order.status,
        total_cost=total_cost,
        number_of_loads=number_of_loads,
        created_at=order.created_at,
        driver_name=driver_name,
        driver_id=driver_id,
        processing_option=order.processing_option
    )