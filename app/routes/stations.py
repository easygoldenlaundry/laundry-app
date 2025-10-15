# app/routes/stations.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel
from sqlalchemy.orm import selectinload 
from sqlalchemy.exc import OperationalError, IntegrityError
from typing import List
from datetime import datetime, timezone 
import asyncio
import logging

from app.db import get_session
from app.models import Order, Machine, Station, Event, Basket, Setting, FinanceEntry
from app.routes.queues import BasketPublic
from app.services.state_machine import apply_transition
from app.sockets import broadcast_machine_update, broadcast_order_update

router = APIRouter(tags=["Stations"])
logger = logging.getLogger(__name__)

class CycleRequest(BaseModel):
    user_id: int

@router.get("/api/baskets/{basket_id}", response_model=BasketPublic)
def get_basket_details(basket_id: int, session: Session = Depends(get_session)):
    """Retrieves full details for a single basket, including its parent order."""
    try:
        basket = session.exec(
            select(Basket)
            .where(Basket.id == basket_id)
            .options(selectinload(Basket.order))
        ).first()
        if not basket:
            raise HTTPException(status_code=404, detail="Basket not found")
        return BasketPublic.from_orm(basket)
    except Exception as e:
        logger.error(f"Error getting basket {basket_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve basket: {str(e)}")

def check_and_promote_order_to_qa(order_id: int, session: Session):
    """Checks if an order is ready to be moved to the QA queue."""
    try:
        order = session.get(Order, order_id)
        if not order or order.status != "Processing":
            return

        baskets = session.exec(select(Basket).where(Basket.order_id == order.id)).all()
        if not baskets:
            return

        if all(b.status == "QA" for b in baskets):
            apply_transition(session, order, "QA", meta={"reason": "All baskets completed processing"})
    except Exception as e:
        logger.error(f"Error checking QA promotion for order {order_id}: {e}")
        # Don't raise - this is a background check


@router.get("/api/stations/{station_type}/machines", response_model=List[Machine])
def get_station_machines(station_type: str, session: Session = Depends(get_session)):
    """
    Returns a list of all machines and their current state for a specific station type.
    """
    try:
        station = session.exec(select(Station).where(Station.type == station_type)).first()
        if not station:
            raise HTTPException(status_code=404, detail=f"Station of type '{station_type}' not found.")
        
        machines = session.exec(select(Machine).where(Machine.station_id == station.id)).all()
        return machines
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting machines for station {station_type}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve machines: {str(e)}")

@router.post("/api/baskets/{basket_id}/start_soaking", response_model=BasketPublic)
async def start_soaking(basket_id: int, request: CycleRequest, session: Session = Depends(get_session)):
    """Sets the soaking start time for a basket with robust error handling."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Use SELECT FOR UPDATE to lock the basket row
            basket = session.exec(
                select(Basket)
                .where(Basket.id == basket_id)
                .options(selectinload(Basket.order))
                .with_for_update()
            ).first()
            
            if not basket:
                raise HTTPException(status_code=404, detail="Basket not found")

            basket.soaking_started_at = datetime.now(timezone.utc)
            basket.updated_at = datetime.now(timezone.utc)
            session.add(basket)
            
            try:
                session.commit()
                session.refresh(basket)
                logger.info(f"Basket {basket_id} soaking started by user {request.user_id}")
            except Exception as commit_error:
                session.rollback()
                logger.error(f"Failed to commit soaking start for basket {basket_id}: {commit_error}")
                raise

            # Broadcast AFTER successful commit
            try:
                order = session.get(Order, basket.order_id)
                await broadcast_order_update(order)
            except Exception as broadcast_error:
                logger.warning(f"Failed to broadcast soaking update for basket {basket_id}: {broadcast_error}")
                # Don't fail the request if broadcast fails
            
            return BasketPublic.from_orm(basket)
            
        except HTTPException:
            raise
        except OperationalError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Database lock conflict for basket {basket_id}, retrying... (attempt {attempt + 1})")
                await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff
                session.rollback()
                continue
            else:
                logger.error(f"Failed to start soaking after {max_retries} attempts: {e}")
                raise HTTPException(status_code=503, detail="Database busy, please try again")
        except Exception as e:
            session.rollback()
            logger.error(f"Unexpected error starting soaking for basket {basket_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to start soaking: {str(e)}")


@router.post("/api/baskets/{basket_id}/start_cycle")
async def start_basket_cycle(basket_id: int, station_type: str, request: CycleRequest, session: Session = Depends(get_session)):
    """
    Assigns a basket to an available machine at a given station with robust locking.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Get station first
            station = session.exec(select(Station).where(Station.type == station_type)).first()
            if not station:
                raise HTTPException(status_code=404, detail=f"Station of type '{station_type}' not found.")

            # Lock an idle machine using SELECT FOR UPDATE to prevent race conditions
            machine = session.exec(
                select(Machine)
                .where(Machine.station_id == station.id, Machine.state == "idle")
                .with_for_update(skip_locked=True)  # Skip locked rows to avoid blocking
                .limit(1)
            ).first()
            
            if not machine:
                raise HTTPException(status_code=409, detail=f"No free machines available at '{station_type}' station.")

            # Lock the basket
            basket = session.exec(
                select(Basket)
                .where(Basket.id == basket_id)
                .with_for_update()
            ).first()
            
            if not basket:
                raise HTTPException(status_code=404, detail=f"Basket {basket_id} not found.")

            # Update machine state
            machine.state = "running"
            machine.current_basket_id = basket_id
            machine.cycle_started_at = datetime.now(timezone.utc)
            session.add(machine)
            
            # Update basket status
            basket.status = f"{station_type.capitalize()}-InProgress"
            basket.updated_at = datetime.now(timezone.utc)
            session.add(basket)

            # Create event
            event = Event(
                order_id=basket.order_id,
                to_status=f"Basket-{basket.id}-Started-{station_type}",
                user_id=request.user_id,
                meta=f'{{"machine_id": {machine.id}, "basket_id": {basket.id}}}'
            )
            session.add(event)
            
            try:
                session.commit()
                session.refresh(machine)
                logger.info(f"Basket {basket_id} started on machine {machine.id} at {station_type}")
            except Exception as commit_error:
                session.rollback()
                logger.error(f"Failed to commit cycle start for basket {basket_id}: {commit_error}")
                raise

            # Broadcast AFTER successful commit
            try:
                machine_with_station = session.exec(
                    select(Machine).options(selectinload(Machine.station)).where(Machine.id == machine.id)
                ).one()
                await broadcast_machine_update(machine_with_station)
            except Exception as broadcast_error:
                logger.warning(f"Failed to broadcast machine update: {broadcast_error}")
                # Don't fail the request if broadcast fails
                
            return {"cycle_time_seconds": machine.cycle_time_seconds, "machine_id": machine.id}
            
        except HTTPException:
            raise
        except OperationalError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Database lock conflict starting cycle for basket {basket_id}, retrying... (attempt {attempt + 1})")
                await asyncio.sleep(0.1 * (attempt + 1))
                session.rollback()
                continue
            else:
                logger.error(f"Failed to start cycle after {max_retries} attempts: {e}")
                raise HTTPException(status_code=503, detail="Database busy, please try again")
        except Exception as e:
            session.rollback()
            logger.error(f"Unexpected error starting cycle for basket {basket_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to start cycle: {str(e)}")


@router.post("/api/baskets/{basket_id}/finish_cycle")
async def finish_basket_cycle(basket_id: int, station_type: str, request: CycleRequest, session: Session = Depends(get_session)):
    """
    Finishes a basket's cycle with robust transaction handling.
    Releases the machine, moves the basket to next state, and tracks costs.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Lock the machine (if any)
            machine = None
            if station_type != "Pretreat":
                machine = session.exec(
                    select(Machine)
                    .where(Machine.current_basket_id == basket_id)
                    .with_for_update()
                ).first()
                
                if not machine:
                    raise HTTPException(status_code=404, detail=f"No machine found running basket ID {basket_id}.")

            # Lock the basket
            basket = session.exec(
                select(Basket)
                .where(Basket.id == basket_id)
                .with_for_update()
            ).first()
            
            if not basket:
                raise HTTPException(status_code=404, detail=f"Basket {basket_id} not found.")

            # Get settings for cost tracking
            all_settings_db = session.exec(select(Setting)).all()
            settings_map = {s.key: s for s in all_settings_db}

            # Track electricity usage
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
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse finance setting '{tracker_key}' or '{usage_key}': {e}")

            # Track maintenance costs
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
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse cost_maintenance_per_cycle setting: {e}")

            # Determine next status
            next_status_map = {
                "Pretreat": "Washing",
                "washing": "Drying",
                "drying": "Folding",
                "folding": "QA"
            }
            next_status = next_status_map.get(station_type)
            if not next_status:
                raise HTTPException(status_code=400, detail=f"Invalid station type '{station_type}' for finishing cycle.")

            # Update machine if exists
            meta_info = {}
            if machine:
                machine.state = "idle"
                machine.current_basket_id = None
                machine.cycle_started_at = None
                session.add(machine)
                meta_info["machine_id"] = machine.id
            
            # Update basket
            basket.status = next_status
            basket.updated_at = datetime.now(timezone.utc)
            if station_type == "Pretreat":
                basket.soaking_started_at = None
            session.add(basket)
            
            # Create event
            event = Event(
                order_id=basket.order_id,
                to_status=f"Basket-{basket.id}-Finished-{station_type}",
                user_id=request.user_id,
                meta=f'{{"basket_id": {basket.id}, "machine_id": {meta_info.get("machine_id")}}}'
            )
            session.add(event)
            
            try:
                session.commit()
                logger.info(f"Basket {basket_id} finished at {station_type}, moved to {next_status}")
            except Exception as commit_error:
                session.rollback()
                logger.error(f"Failed to commit cycle finish for basket {basket_id}: {commit_error}")
                raise

            # Check for QA promotion (in separate try block)
            if next_status == "QA":
                try:
                    check_and_promote_order_to_qa(basket.order_id, session)
                except Exception as qa_error:
                    logger.warning(f"Error checking QA promotion for order {basket.order_id}: {qa_error}")
            
            # Broadcast updates AFTER successful commit
            try:
                if machine:
                    session.refresh(machine)
                    machine_with_station = session.exec(
                        select(Machine).options(selectinload(Machine.station)).where(Machine.id == machine.id)
                    ).one()
                    await broadcast_machine_update(machine_with_station)

                order = session.get(Order, basket.order_id)
                await broadcast_order_update(order)
            except Exception as broadcast_error:
                logger.warning(f"Failed to broadcast updates for basket {basket_id}: {broadcast_error}")
                # Don't fail the request if broadcast fails

            return {"message": f"Basket {basket_id} finished at {station_type} and moved to {next_status}."}
            
        except HTTPException:
            raise
        except OperationalError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Database lock conflict finishing cycle for basket {basket_id}, retrying... (attempt {attempt + 1})")
                await asyncio.sleep(0.1 * (attempt + 1))
                session.rollback()
                continue
            else:
                logger.error(f"Failed to finish cycle after {max_retries} attempts: {e}")
                raise HTTPException(status_code=503, detail="Database busy, please try again")
        except Exception as e:
            session.rollback()
            logger.error(f"Unexpected error finishing cycle for basket {basket_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to finish cycle: {str(e)}")
