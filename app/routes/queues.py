# app/routes/queues.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List, Union, Optional
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from datetime import datetime

from app.db import get_session
from app.models import Order, Basket, Bag

router = APIRouter(prefix="/api/queues", tags=["Queues"])

# --- Pydantic models for clear API responses ---

class BagForQueue(BaseModel):
    bag_code: str

    class Config:
        orm_mode = True

class OrderForQueue(BaseModel):
    id: int
    customer_name: str
    bags: List[BagForQueue] = []
    dispatch_method: Optional[str] = None

    class Config:
        orm_mode = True

class OrderForBasket(BaseModel):
    id: int
    customer_name: str

    class Config:
        orm_mode = True

class BasketPublic(BaseModel):
    id: int
    order_id: int
    basket_index: int
    status: str
    order: OrderForBasket
    soaking_started_at: Optional[datetime] = None

    class Config:
        orm_mode = True

class QASummaryItem(BaseModel):
    order: Order
    baskets_at_qa: int
    total_baskets: int

    class Config:
        orm_mode = True

# A single map to define all station queue types.
STATION_TYPE_MAP = {
    "deliveredtohub": ("Order", "DeliveredToHub"),
    "imaging": ("Order", "Imaging"),
    "pretreat": ("Basket", "Pretreat"),
    "washing": ("Basket", "Washing"),
    "drying": ("Basket", "Drying"),
    "folding": ("Basket", "Folding"),
}

@router.get("/qa/ready", response_model=List[Order])
def get_qa_ready_queue(hub_id: int = 1, session: Session = Depends(get_session)):
    """Returns orders that are fully ready for QA."""
    statement = (
        select(Order)
        .where(Order.hub_id == hub_id, Order.status == "QA")
        .order_by(Order.created_at.asc())
    )
    orders = session.exec(statement).all()
    return orders

@router.get("/qa/summary", response_model=List[QASummaryItem])
def get_qa_summary(hub_id: int = 1, session: Session = Depends(get_session)):
    """
    Returns orders in processing that have at least one, but not all, baskets
    at the QA station.
    """
    orders_in_processing = session.exec(
        select(Order)
        .where(Order.hub_id == hub_id, Order.status == "Processing")
        .options(selectinload(Order.baskets))
    ).all()

    summary_list = []
    for order in orders_in_processing:
        if not order.baskets:
            continue
        
        baskets_at_qa = sum(1 for b in order.baskets if b.status == "QA")
        total_baskets = len(order.baskets)
        
        if 0 < baskets_at_qa < total_baskets:
            summary_list.append(QASummaryItem(
                order=order,
                baskets_at_qa=baskets_at_qa,
                total_baskets=total_baskets
            ))
            
    return summary_list

@router.get("/{hub_id}/{station_type}", response_model=Union[List[OrderForQueue], List[BasketPublic]])
def get_station_queue(
    hub_id: int,
    station_type: str,
    session: Session = Depends(get_session)
):
    """
    Returns the work queue for a given station.
    - For 'deliveredtohub' and 'imaging', it returns whole Orders with bag info.
    - For 'pretreat', 'washing', etc., it returns individual Baskets.
    """
    lookup = STATION_TYPE_MAP.get(station_type.lower())
    if not lookup:
        raise HTTPException(status_code=404, detail=f"Invalid station type for queue: {station_type}")

    queue_model_type, target_status = lookup

    if queue_model_type == "Order":
        statement = (
            select(Order)
            .where(Order.hub_id == hub_id, Order.status == target_status)
            .options(selectinload(Order.bags))
            .order_by(Order.created_at.asc())
        )
        results = session.exec(statement).all()
        return results
    
    elif queue_model_type == "Basket":
        statement = (
            select(Basket)
            .join(Order)
            .where(Order.hub_id == hub_id, Basket.status == target_status)
            .options(selectinload(Basket.order))
            .order_by(Basket.created_at.asc())
        )
        results = session.exec(statement).all()
        return [BasketPublic.from_orm(b) for b in results]
    
    raise HTTPException(status_code=500, detail="Internal server error in queue logic.")