# app/routes/qa.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session
from pydantic import BaseModel
import secrets

from app.db import get_session
from app.models import Order, Basket
from app.services.state_machine import apply_transition
from app.services.dispatch import dispatch_delivery_for_order
from app.auth import get_current_hybrid_staff_user

router = APIRouter(
    prefix="/api/orders",
    tags=["QA"],
    dependencies=[Depends(get_current_hybrid_staff_user)]
)

class QARequest(BaseModel):
    user_id: int
    passed: bool
    notes: str

@router.post("/{order_id}/qa", response_model=Order)
def process_qa_decision(
    order_id: int,
    request: QARequest,
    session: Session = Depends(get_session)
):
    """
    Processes the result of a Quality Assurance check.
    - If passed, it moves the order to 'ReadyForDelivery'.
    - If failed, it sends the order back for re-processing by resetting basket statuses.
    """
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "QA":
        raise HTTPException(status_code=400, detail=f"Order is not in QA status, but '{order.status}'")

    if request.passed:
        if not order.delivery_pin:
             order.delivery_pin = str(secrets.randbelow(10000)).zfill(4)
        session.add(order)
        dispatch_delivery_for_order(session, order, request.user_id)
    else:
        # On fail, reset all baskets to Pretreat and move the order back to Processing.
        baskets = session.query(Basket).filter(Basket.order_id == order_id).all()
        for basket in baskets:
            basket.status = "Pretreat"
            session.add(basket)
        
        meta = {
            "qa_failed_by": request.user_id,
            "qa_notes": request.notes,
            "reason": "Resetting all baskets to Pretreat"
        }
        apply_transition(session, order, "Processing", user_id=request.user_id, meta=meta)

    session.refresh(order)
    return order