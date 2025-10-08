# app/routes/stations.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, update
from pydantic import BaseModel
from sqlalchemy.orm import selectinload 
from typing import List
from datetime import datetime, timezone 
import asyncio

from app.db import get_session
from app.models import Order, Machine, Station, Event, Basket, Setting, FinanceEntry
from app.routes.queues import BasketPublic
from app.services.state_machine import apply_transition
from app.sockets import broadcast_machine_update, broadcast_order_update, broadcast_basket_update

router = APIRouter(tags=["Stations"])

class CycleRequest(BaseModel):
    user_id: int

@router.get("/api/baskets/{basket_id}", response_model=BasketPublic)
def get_basket_details(basket_id: int, session: Session = Depends(get_session)):
    """Retrieves full details for a single basket, including its parent order."""
    basket = session.exec(
        select(Basket)
        .where(Basket.id == basket_id)
        .options(selectinload(Basket.order))
    ).first()
    if not basket:
        raise HTTPException(status_code=404, detail="Basket not found")
    return BasketPublic.from_orm(basket)

def check_and_promote_order_to_qa(order_id: int, session: Session):
    """Checks if an order is ready to be moved to the QA queue."""
    order = session.get(Order, order_id)
    if not order or order.status != "Processing":
        return

    baskets = session.exec(select(Basket).where(Basket.order_id == order.id)).all()
    if not baskets:
        return

    if all(b.status == "QA" for b in baskets):
        apply_transition(session, order, "QA", meta={"reason": "All baskets completed processing"})


@router.get("/api/stations/{station_type}/machines", response_model=List[Machine])
def get_station_machines(station_type: str, session: Session = Depends(get_session)):
    """
    Returns a list of all machines and their current state for a specific station type.
    """
    station = session.exec(select(Station).where(Station.type == station_type)).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station of type '{station_type}' not found.")
    
    machines = session.exec(select(Machine).where(Machine.station_id == station.id)).all()
    return machines

@router.post("/api/baskets/{basket_id}/start_soaking", response_model=Basket)
async def start_soaking(basket_id: int, request: CycleRequest, session: Session = Depends(get_session)):
    """Sets the soaking start time for a basket."""
    basket = session.get(Basket, basket_id)
    if not basket:
        raise HTTPException(status_code=404, detail="Basket not found")

    basket.soaking_started_at = datetime.now(timezone.utc)
    session.add(basket)
    session.commit()
    session.refresh(basket)

    order = session.get(Order, basket.order_id)
    await broadcast_order_update(order)
    return basket


@router.post("/api/baskets/{basket_id}/start_cycle")
async def start_basket_cycle(basket_id: int, station_type: str, request: CycleRequest, session: Session = Depends(get_session)):
    """
    Assigns a basket to an available machine at a given station.
    """
    station = session.exec(select(Station).where(Station.type == station_type)).first()
    if not station:
        raise HTTPException(status_code=404, detail=f"Station of type '{station_type}' not found.")

    machine = session.exec(select(Machine).where(Machine.station_id == station.id, Machine.state == "idle")).first()
    if not machine:
        raise HTTPException(status_code=409, detail=f"No free machines available at '{station_type}' station.")

    basket = session.get(Basket, basket_id)
    if not basket:
        raise HTTPException(status_code=404, detail=f"Basket {basket_id} not found.")

    machine.state = "running"
    machine.current_basket_id = basket_id
    machine.cycle_started_at = datetime.now(timezone.utc)
    session.add(machine)
    
    basket.status = f"{station_type.capitalize()}-InProgress"
    session.add(basket)

    event = Event(
        order_id=basket.order_id,
        to_status=f"Basket-{basket.id}-Started-{station_type}",
        user_id=request.user_id,
        meta=f'{{"machine_id": {machine.id}, "basket_id": {basket.id}}}'
    )
    session.add(event)
    session.commit()
    session.refresh(machine)

    machine_with_station = session.exec(
        select(Machine).options(selectinload(Machine.station)).where(Machine.id == machine.id)
    ).one()
    
    await broadcast_machine_update(machine_with_station)
        
    return {"cycle_time_seconds": machine.cycle_time_seconds, "machine_id": machine.id}


@router.post("/api/baskets/{basket_id}/finish_cycle")
async def finish_basket_cycle(basket_id: int, station_type: str, request: CycleRequest, session: Session = Depends(get_session)):
    """
    Finishes a basket's cycle, releases the machine, moves the basket to the
    next state, and checks if the parent order can be moved to QA.
    Also tracks electricity, water, and maintenance costs.
    """
    machine = session.exec(select(Machine).where(Machine.current_basket_id == basket_id)).first()
    
    if station_type != "Pretreat" and not machine:
        raise HTTPException(status_code=404, detail=f"No machine found running basket ID {basket_id}.")

    basket = session.get(Basket, basket_id)
    if not basket:
         raise HTTPException(status_code=404, detail=f"Basket {basket_id} not found.")

    all_settings_db = session.exec(select(Setting)).all()
    settings_map = {s.key: s for s in all_settings_db}

    settings_to_increment = {}
    if station_type == "washing":
        settings_to_increment = {"monthly_tracker_electricity_kwh": "usage_kwh_per_wash"}
    elif station_type == "drying":
        settings_to_increment = {"monthly_tracker_electricity_kwh": "usage_kwh_per_dry"}
    
    for tracker_key, usage_key in settings_to_increment.items():
        tracker_setting = settings_map.get(tracker_key)
        usage_setting = settings_map.get(usage_key)

        if tracker_setting and usage_setting:
            try:
                current_value = float(tracker_setting.value)
                amount_to_add = float(usage_setting.value)
                tracker_setting.value = str(current_value + amount_to_add)
                session.add(tracker_setting)
            except (ValueError, TypeError):
                print(f"Warning: Could not parse finance setting '{tracker_key}' or '{usage_key}' as a number.")

    if station_type in ["washing", "drying"]:
        maintenance_cost_setting = settings_map.get("cost_maintenance_per_cycle")
        if maintenance_cost_setting:
            try:
                cost = float(maintenance_cost_setting.value)
                if cost > 0:
                    session.add(FinanceEntry(
                        order_id=basket.order_id,
                        entry_type='variable_cost',
                        amount=cost,
                        description=f"Machine Maintenance ({station_type})"
                    ))
            except (ValueError, TypeError):
                print("Warning: Could not parse cost_maintenance_per_cycle setting.")

    next_status_map = {
        "Pretreat": "Washing",
        "washing": "Drying",
        "drying": "Folding",
        "folding": "QA"
    }
    next_status = next_status_map.get(station_type)
    if not next_status:
        raise HTTPException(status_code=400, detail=f"Invalid station type '{station_type}' for finishing cycle.")

    meta_info = {}
    if machine:
        machine.state = "idle"
        machine.current_basket_id = None
        machine.cycle_started_at = None
        session.add(machine)
        meta_info["machine_id"] = machine.id
    
    basket.status = next_status
    basket.updated_at = datetime.now(timezone.utc)
    if station_type == "Pretreat":
        basket.soaking_started_at = None
    session.add(basket)
    
    event = Event(
        order_id=basket.order_id,
        to_status=f"Basket-{basket.id}-Finished-{station_type}",
        user_id=request.user_id,
        meta=f'{{"basket_id": {basket.id}, "machine_id": {meta_info.get("machine_id")}}}'
    )
    session.add(event)
    
    session.commit()

    if next_status == "QA":
        check_and_promote_order_to_qa(basket.order_id, session)
    
    if machine:
        session.refresh(machine)
        machine_with_station = session.exec(
            select(Machine).options(selectinload(Machine.station)).where(Machine.id == machine.id)
        ).one()
        await broadcast_machine_update(machine_with_station)

    order = session.get(Order, basket.order_id)
    await broadcast_order_update(order)
    
    # Broadcast basket update to notify the next station
    await broadcast_basket_update(basket, order.hub_id)

    return {"message": f"Basket {basket_id} finished at {station_type} and moved to {next_status}."}