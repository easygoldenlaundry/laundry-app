# app/routes/orders.py
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
from sqlmodel import Session, select, delete, update
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone

from app.db import get_session
from app.models import Order, Bag, Image, Item, Basket, User, Message, Customer
from app.services.state_machine import apply_transition
from app.auth import get_current_admin_user, get_current_api_user # Use the working admin auth
from app.sockets import broadcast_message_update, broadcast_admin_notification
from app.config import DATA_ROOT
import aiofiles
import os

router = APIRouter(prefix="/api/orders", tags=["Orders"])

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
        driver_user = session.get(User, order.assigned_driver_id)
        if driver_user:
            driver_info = DriverPublic(id=driver_user.id, display_name=driver_user.display_name)
    
    return OrderWithDriverResponse(order=order, driver=driver_info)


@router.get("/active", response_model=List[Order])
async def get_active_orders(
    hub_id: int = 1,
    user: User = Depends(get_current_admin_user), # Correct admin-only auth for this endpoint
    session: Session = Depends(get_session)
):
    """
    Returns a list of all orders that are not in a final state
    (e.g., 'Delivered' or 'Closed'). Eager loads baskets for dashboard view.
    """
    statement = select(Order).where(
        Order.hub_id == hub_id,
        Order.status != "Delivered",
        Order.status != "Closed"
    ).options(selectinload(Order.baskets)).order_by(Order.created_at.desc())
    results = session.exec(statement).all()
    
    return [order.dict() for order in results]

# ... (rest of the file is unchanged) ...
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
def request_delivery(order_id: int, delivery_request: DeliveryRequest, session: Session = Depends(get_session)):
    """
    Customer-triggered action to set delivery details and move an order to 'OutForDelivery'.
    """
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "ReadyForDelivery":
        raise HTTPException(status_code=400, detail="Order is not ready for delivery request.")

    # Update customer profile with new delivery details
    customer = session.get(Customer, order.customer_id)
    if customer:
        customer.address = delivery_request.delivery_address
        customer.latitude = delivery_request.delivery_latitude
        customer.longitude = delivery_request.delivery_longitude
        customer.phone_number = delivery_request.phone
        session.add(customer)

    updated_order = apply_transition(session, order, "OutForDelivery", meta={"customer_triggered": True})
    return updated_order

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
    user: User = Depends(get_current_api_user),
    session: Session = Depends(get_session)
):
    order = session.get(Order, order_id)
    if not order: raise HTTPException(404, "Order not found")
    
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

    socket_msg = { "order_id": new_message.order_id, "sender_role": new_message.sender_role, "content": new_message.content, "timestamp": new_message.timestamp.isoformat() }
    await broadcast_message_update(socket_msg)
    
    if sender_role == "customer":
        await broadcast_admin_notification("new_customer_message")
    
    return MessagePublic(**message_dict)

@router.post("/{order_id}/messages/mark-read", status_code=204)
def mark_messages_as_read(
    order_id: int,
    user: User = Depends(get_current_api_user),
    session: Session = Depends(get_session)
):
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