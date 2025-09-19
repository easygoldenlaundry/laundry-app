# app/routes/claims.py
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File
from sqlmodel import Session, select
import aiofiles
import os

from app.db import get_session
from app.models import Order, Claim
from app.services.state_machine import apply_transition
from app.config import DATA_ROOT

router = APIRouter(prefix="/api", tags=["Claims"])

@router.post("/orders/{order_id}/claims")
async def create_claim(
    order_id: int,
    claim_type: str = Form(...),
    description: str = Form(...),
    image: Optional[UploadFile] = File(None),
    session: Session = Depends(get_session)
):
    """
    Creates a claim for an order and applies auto-resolution rules.
    """
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    new_claim = Claim(
        order_id=order_id,
        claim_type=claim_type,
        notes=description,
        status="open" 
    )
    
    session.add(new_claim)
    session.commit()
    session.refresh(new_claim)

    # --- Auto-Resolution Logic ---

    # 1. Delayed Order Claim
    if claim_type == "delay" and order.sla_deadline and order.sla_deadline < datetime.now(timezone.utc):
        new_claim.status = "resolved"
        new_claim.amount = 50.00
        new_claim.resolved_at = datetime.now(timezone.utc)
        new_claim.notes += "\n[Auto-resolved: SLA breached]"
        session.add(new_claim)
        session.commit()
        session.refresh(new_claim)

    # 2. Missed Stain Claim
    elif claim_type == "missed_stain":
        new_claim.status = "awaiting_rewash"
        session.add(new_claim)
        # Transition the order back to the Pretreat station for re-processing
        apply_transition(session, order, "Pretreat", meta={"claim_id": new_claim.id, "reason": "missed_stain"})
        session.refresh(new_claim)

    return new_claim