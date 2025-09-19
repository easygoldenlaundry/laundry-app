# app/routes/bags.py
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlmodel import Session, select
from pydantic import BaseModel

from app.db import get_session
from app.models import Order, Bag
from app.services.state_machine import apply_transition

router = APIRouter()

class BagScanRequest(BaseModel):
    bag_code: str
    order_id: int
    user_id: int # Assuming a user_id is sent from the frontend

@router.post("/api/bags/scan", response_model=Bag)
def scan_bag(
    scan_request: BagScanRequest,
    session: Session = Depends(get_session)
):
    """
    Associates a scanned bag with an order and moves the order directly to the 'Imaging' state.
    This endpoint is idempotent.
    """
    order = session.get(Order, scan_request.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Idempotency Check 1: If order is already past the 'Imaging' stage, do nothing.
    if order.status not in ["PickedUp", "DeliveredToHub", "AtHub", "Imaging"]:
        existing_bag = session.exec(select(Bag).where(Bag.order_id == order.id)).first()
        if existing_bag:
            return existing_bag
        raise HTTPException(status_code=200, detail="Order is already in processing.")

    # Check if the bag_code is already in use by another order
    existing_bag_other_order = session.exec(
        select(Bag).where(Bag.bag_code == scan_request.bag_code, Bag.order_id != scan_request.order_id)
    ).first()

    if existing_bag_other_order:
        raise HTTPException(status_code=409, detail=f"Bag code '{scan_request.bag_code}' is already assigned to another order.")

    # Check if this bag already exists for this order
    bag = session.exec(
        select(Bag).where(Bag.bag_code == scan_request.bag_code, Bag.order_id == scan_request.order_id)
    ).first()

    if not bag:
        bag = Bag(
            bag_code=scan_request.bag_code,
            order_id=scan_request.order_id,
            scanned_at=datetime.now(timezone.utc),
            sealed=True
        )
        session.add(bag)
        session.commit()
        session.refresh(bag)

    # --- State Transition ---
    # FIX: The goal of intake is to send the order to the FIRST station. We now transition
    # directly to 'Imaging' instead of the generic 'AtHub'.
    intake_statuses = {"PickedUp", "DeliveredToHub", "AtHub"}
    
    if order.status in intake_statuses:
        apply_transition(session, order, "Imaging", user_id=scan_request.user_id, meta={"bag_code": bag.bag_code})
    
    return bag