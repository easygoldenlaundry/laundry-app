# app/routes/orders.py
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
from sqlmodel import Session, select, delete
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone

from app.db import get_session
from app.models import Order, Bag, Image, Item, Basket
from app.services.state_machine import apply_transition
from app.config import DATA_ROOT
import aiofiles
import os

router = APIRouter(prefix="/api/orders", tags=["Orders"])


class ImageCompletionRequest(BaseModel):
    user_id: int
    basket_count: int


@router.get("/active", response_model=List[Order])
def get_active_orders(hub_id: int, session: Session = Depends(get_session)):
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
    return results

@router.get("/{order_id}/bag", response_model=Bag)
def get_order_bag(order_id: int, session: Session = Depends(get_session)):
    """Retrieve the bag associated with a specific order."""
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
    """
    Uploads an image for a specific item and CREATES the item record dynamically.
    This is now the source of truth for item creation.
    """
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
    """
    Finalizes imaging, creates individual baskets for the order, and moves the
    order into the 'Processing' state.
    """
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    items_in_order = session.exec(select(Item).where(Item.order_id == order_id)).all()
    if not items_in_order:
        raise HTTPException(status_code=400, detail="Cannot complete imaging with 0 items scanned.")
    
    # --- [MODIFIED] ---
    order.total_items = len(items_in_order)
    order.imaged_items_count = len(items_in_order)
    order.imaging_completed_at = datetime.now(timezone.utc)
    order.basket_count = request.basket_count
    # --- End of [MODIFIED] ---
    
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
def request_delivery(order_id: int, session: Session = Depends(get_session)):
    """
    Customer-triggered action to move an order from 'ReadyForDelivery' to 'OutForDelivery',
    making it available for drivers.
    """
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "ReadyForDelivery":
        raise HTTPException(status_code=400, detail="Order is not ready for delivery request.")
        
    updated_order = apply_transition(session, order, "OutForDelivery", meta={"customer_triggered": True})
    return updated_order

@router.get("/{order_id}/stained-images", response_model=List[Image])
def get_stained_images(order_id: int, session: Session = Depends(get_session)):
    """Returns all images for an order that were flagged for stains."""
    images = session.exec(
        select(Image).where(Image.order_id == order_id, Image.is_stain == True)
    ).all()
    return images


class QAImageUpdateRequest(BaseModel):
    qa_status: str # 'removed', 'non_removable', 'retry'
    qa_notes: Optional[str] = None

@router.post("/images/{image_id}/qa-update", response_model=Image)
def update_image_qa_status(image_id: int, request: QAImageUpdateRequest, session: Session = Depends(get_session)):
    """Updates the QA status of a single image."""
    image = session.get(Image, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    image.qa_status = request.qa_status
    image.qa_notes = request.qa_notes
    session.add(image)
    session.commit()
    session.refresh(image)
    return image