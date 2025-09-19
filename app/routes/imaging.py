# app/routes/imaging.py
import os
import uuid
import aiofiles
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import Optional

from app.db import get_session
from app.models import Order, Image, Bag, Item
from app.services.state_machine import apply_transition
from app.config import DATA_ROOT

router = APIRouter()

@router.get("/api/orders/{order_id}/bag", response_model=Bag)
def get_order_bag(order_id: int, session: Session = Depends(get_session)):
    """Retrieves the bag associated with the order."""
    bag = session.exec(select(Bag).where(Bag.order_id == order_id)).first()
    if not bag:
        raise HTTPException(status_code=404, detail="Bag not found for this order. Ensure intake was completed.")
    return bag

@router.post("/api/orders/{order_id}/upload-image")
async def upload_image(
    order_id: int,
    bag_id: int = Form(...),
    item_index: int = Form(...),
    user_id: int = Form(...),
    is_stain: bool = Form(...),
    proof_photo: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    """Handles image upload, saves file, and creates Image DB record."""
    
    order = session.get(Order, order_id)
    bag = session.get(Bag, bag_id)
    
    if not order or not bag:
        raise HTTPException(status_code=404, detail="Order or Bag not found")

    # 1. Save File
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    filename = f"{timestamp}_item{item_index}.jpg"
    save_dir = os.path.join(DATA_ROOT, "orders", str(order_id), "images")
    os.makedirs(save_dir, exist_ok=True)
    file_path_full = os.path.join(save_dir, filename)
    
    async with aiofiles.open(file_path_full, "wb") as buffer:
        while content := await proof_photo.read(1024 * 1024):
            await buffer.write(content)

    db_path = os.path.join("orders", str(order_id), "images", filename)
    
    # 2. Create Item and Image records
    item_record = Item(
        order_id=order_id,
        bag_id=bag_id,
        name=f"Item #{item_index}",
        imaged=True,
        stain_flags="stain_detected" if is_stain else None
    )
    session.add(item_record)
    session.commit()
    session.refresh(item_record)

    image_record = Image(
        order_id=order_id,
        bag_id=bag_id,
        item_id=item_record.id,
        path=db_path.replace("\\", "/"),
        image_type="imaging_scan",
        uploaded_by=user_id,
        is_stain=is_stain
    )
    session.add(image_record)
        
    session.commit()
    session.refresh(image_record)
    
    return {"image_id": image_record.id, "path": image_record.path}