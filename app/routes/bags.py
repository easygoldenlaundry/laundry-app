# app/routes/bags.py
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlmodel import Session, select
from pydantic import BaseModel

from app.db import get_session
from app.models import Order, Bag
# --- THIS IS THE FIX: Added the missing import ---
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
    Verifies a scanned bag against the order's pre-assigned bag and moves the order to 'Imaging'.
    """
    order = session.get(Order, scan_request.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Idempotency Check: If order is already past the intake stage, do nothing.
    if order.status not in ["PickedUp", "DeliveredToHub", "AtHub"]:
        existing_bag = session.exec(select(Bag).where(Bag.order_id == order.id)).first()
        if existing_bag and existing_bag.bag_code == scan_request.bag_code:
            return existing_bag # Return success if it's already done correctly.
        raise HTTPException(status_code=400, detail="Order is already in processing and cannot be scanned again.")

    # --- THIS IS THE FIX: Verify the scanned code against the pre-assigned one ---
    expected_bag = session.exec(select(Bag).where(Bag.order_id == scan_request.order_id)).first()
    if not expected_bag:
        raise HTTPException(status_code=404, detail=f"No bag has been pre-assigned for Order #{order.id}.")
    
    if expected_bag.bag_code != scan_request.bag_code:
        raise HTTPException(status_code=400, detail=f"Incorrect bag. Scanned '{scan_request.bag_code}', but expected '{expected_bag.bag_code}'.")
    
    # If we reach here, the code is correct. Update the bag's status.
    expected_bag.scanned_at = datetime.now(timezone.utc)
    expected_bag.sealed = True 
    session.add(expected_bag)

    # Transition the order state to the first station.
    apply_transition(session, order, "Imaging", user_id=scan_request.user_id, meta={"bag_code": expected_bag.bag_code})
    
    return expected_bag