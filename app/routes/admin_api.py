# app/routes/admin_api.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select, func, update
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict
from datetime import datetime, timezone
import json

from app.db import get_session
from app.models import User, Station, Machine, Claim, Order, Setting, Message, InventoryItem
from app.services.state_machine import apply_transition
from app.services.finance_calculator import create_finance_entries_for_order
from app.auth import get_current_admin_user
from app.sockets import broadcast_admin_notification, broadcast_settings_update

router = APIRouter(
    prefix="/api/admin", 
    tags=["Admin API"], 
    dependencies=[Depends(get_current_admin_user)]
)

# --- User Management API ---

@router.get("/users", response_model=List[User])
def get_users(session: Session = Depends(get_session)):
    """Lists all non-customer users for the approval dashboard."""
    return session.exec(select(User).where(User.role.in_(["driver", "staff"]))).all()

@router.post("/users/{user_id}/toggle_activation", response_model=User)
def toggle_user_activation(user_id: int, session: Session = Depends(get_session)):
    user = session.get(User, user_id)
    if not user: raise HTTPException(404, "User not found")
    if user.role == "admin": raise HTTPException(400, "Cannot deactivate an admin.")
    user.is_active = not user.is_active
    session.add(user); session.commit(); session.refresh(user)
    return user

class PermissionsUpdateRequest(BaseModel):
    allowed_stations: List[str]

@router.post("/users/{user_id}/permissions", response_model=User)
def update_user_permissions(user_id: int, request: PermissionsUpdateRequest, session: Session = Depends(get_session)):
    """Updates the station permissions for a staff user."""
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != "staff":
        raise HTTPException(status_code=400, detail="Permissions can only be set for staff members.")

    user.allowed_stations = ",".join(request.allowed_stations)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


# --- Uber Dispatch & Chat API ---
class UberOrderPublic(Order):
    unread_message_count: int

@router.get("/uber-orders", response_model=List[UberOrderPublic])
def get_uber_dispatch_orders(session: Session = Depends(get_session)):
    """
    Gets all active Uber orders, plus any completed orders that have unread messages.
    """
    TERMINAL_STATUSES = ["Delivered", "Closed"]
    
    active_orders = session.exec(
        select(Order)
        .where(Order.dispatch_method == "uber", Order.status.notin_(TERMINAL_STATUSES))
    ).all()
    
    completed_with_unread = session.exec(
        select(Order).join(Message).where(
            Order.dispatch_method == "uber",
            Order.status.in_(TERMINAL_STATUSES),
            Message.sender_role == 'customer',
            Message.is_read == False
        ).distinct()
    ).all()
    
    all_orders_map = {o.id: o for o in active_orders}
    for order in completed_with_unread:
        if order.id not in all_orders_map:
            all_orders_map[order.id] = order

    response_orders = []
    sorted_orders = sorted(all_orders_map.values(), key=lambda o: o.created_at)

    for order in sorted_orders:
        unread_count = session.exec(
            select(func.count(Message.id))
            .where(
                Message.order_id == order.id,
                Message.is_read == False,
                Message.sender_role == 'customer'
            )
        ).one()
        order_data = UberOrderPublic.from_orm(order, update={'unread_message_count': unread_count})
        response_orders.append(order_data)

    return response_orders

@router.get("/orders/active", response_model=List[Order])
async def get_active_orders(hub_id: int = 1, session: Session = Depends(get_session)):
    """
    Returns a list of all orders that are not in a final state
    (e.g., 'Delivered' or 'Closed'). Eager loads baskets for dashboard view.
    Admin-only endpoint for the dashboard.
    """
    from sqlalchemy.orm import selectinload
    
    statement = select(Order).where(
        Order.hub_id == hub_id,
        Order.status != "Delivered",
        Order.status != "Closed"
    ).options(selectinload(Order.baskets)).order_by(Order.created_at.desc())
    results = session.exec(statement).all()
    
    return [order.dict() for order in results]

@router.get("/unread-count")
def get_total_unread_message_count(session: Session = Depends(get_session)):
    """Gets the total count of unread messages from customers across all orders."""
    unread_count = session.exec(
        select(func.count(Message.id))
        .where(Message.is_read == False, Message.sender_role == 'customer')
    ).one()
    return {"unread_count": unread_count}

class UberStatusUpdateRequest(BaseModel):
    order_id: int
    action: Literal["picked_up", "delivered_to_hub", "picked_up_from_hub", "delivered_to_customer"]

@router.post("/uber-orders/update-status", response_model=Order)
def update_uber_order_status(
    request: UberStatusUpdateRequest,
    background_tasks: BackgroundTasks,
    admin_user: User = Depends(get_current_admin_user),
    session: Session = Depends(get_session)
):
    """Allows an admin to manually update the status of an Uber order for both pickup and delivery."""
    order = session.get(Order, request.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.dispatch_method != "uber":
        raise HTTPException(status_code=400, detail="This order is not an Uber dispatch.")
    
    target_status_map = {
        "picked_up": "PickedUp",
        "delivered_to_hub": "DeliveredToHub",
        "picked_up_from_hub": "OnRouteToCustomer",
        "delivered_to_customer": "Delivered"
    }
    target_status = target_status_map.get(request.action)

    if not target_status:
        raise HTTPException(status_code=400, detail="Invalid action.")

    updated_order = apply_transition(
        session, order, target_status, user_id=admin_user.id, meta={"manual_uber_update": True}
    )

    if target_status == "Delivered":
        background_tasks.add_task(create_finance_entries_for_order, order_id=order.id, session=session)

    return updated_order

@router.post("/orders/{order_id}/resolve-chat")
async def resolve_chat_for_order(order_id: int, session: Session = Depends(get_session)):
    """Marks all customer messages for an order as read. Used by admins to dismiss a chat."""
    statement = (
        update(Message)
        .where(Message.order_id == order_id, Message.sender_role == 'customer')
        .values(is_read=True)
    )
    session.exec(statement)
    session.commit()
    
    await broadcast_admin_notification("unread_count_updated")

    return {"message": "Chat resolved. All messages marked as read."}

# --- Settings API ---

@router.get("/settings", response_model=Dict[str, str])
def get_all_settings(session: Session = Depends(get_session)):
    """Retrieves all application settings as a key-value dictionary."""
    settings = session.exec(select(Setting)).all()
    return {s.key: s.value for s in settings}

class SingleSettingUpdate(BaseModel):
    value: str

@router.post("/settings/{key}", status_code=200)
def update_single_setting(
    key: str,
    request: SingleSettingUpdate,
    session: Session = Depends(get_session)
):
    """Updates the value of a single setting by its key."""
    setting = session.get(Setting, key)
    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting with key '{key}' not found.")
    
    setting.value = request.value
    session.add(setting)
    session.commit()
    return {"message": f"Setting '{key}' updated successfully."}

def reconcile_machines(session: Session, station_type: str, new_count: int, cycle_time: int):
    station = session.exec(select(Station).where(Station.type == station_type)).first()
    if not station: return
    current_machines = session.exec(select(Machine).where(Machine.station_id == station.id)).all()
    diff = new_count - len(current_machines)
    if diff > 0:
        for _ in range(diff):
            session.add(Machine(station_id=station.id, type=station.type.removesuffix('ing'), cycle_time_seconds=cycle_time))
    elif diff < 0:
        idle_machines = [m for m in current_machines if m.state == "idle"]
        for i in range(min(abs(diff), len(idle_machines))):
            session.delete(idle_machines[i])

def update_inventory_items(session: Session, inventory_data_json: str):
    """Creates or updates inventory items from a JSON string provided by the settings page."""
    try:
        inventory_data = json.loads(inventory_data_json)
        for item_data in inventory_data:
            sku = item_data.get('sku')
            if not sku: continue
            
            item = session.get(InventoryItem, sku)
            if not item:
                item = InventoryItem(sku=sku)
            
            item.name = item_data.get('name')
            item.unit_of_measurement = item_data.get('unit')
            item.low_stock_threshold = float(item_data.get('threshold', 0))
            session.add(item)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid inventory data format: {e}")

@router.post("/settings")
def update_settings(request: Dict[str, str], session: Session = Depends(get_session)):
    """Updates multiple settings and reconciles machines and inventory."""
    inventory_data_json = request.pop("inventory_items_json", "[]")

    for key, value in request.items():
        setting = session.get(Setting, key)
        if setting:
            setting.value = value
            session.add(setting)
        else:
            # Create new setting if it doesn't exist
            new_setting = Setting(key=key, value=value)
            session.add(new_setting)
    
    update_inventory_items(session, inventory_data_json)
    
    try:
        reconcile_machines(session, "washing", int(request.get("washing_machine_count", 1)), int(request.get("wash_cycle_time_seconds", 1800)))
        reconcile_machines(session, "drying", int(request.get("drying_machine_count", 1)), int(request.get("dry_cycle_time_seconds", 2400)))
        reconcile_machines(session, "folding", int(request.get("folding_machine_count", 1)), int(request.get("fold_cycle_time_seconds", 300)))
    except Exception as e:
        print(f"Could not reconcile machines: {e}")

    # Update station capacities
    try:
        update_station_capacity(session, "imaging", int(request.get("imaging_station_capacity", 5)))
        update_station_capacity(session, "pretreat", int(request.get("pretreat_station_capacity", 5)))
        update_station_capacity(session, "qa", int(request.get("qa_station_capacity", 5)))
    except Exception as e:
        print(f"Could not update station capacities: {e}")

    session.commit()

    # Broadcast the settings update to all connected clients
    import asyncio
    asyncio.create_task(broadcast_settings_update())

    return {"message": "Settings updated successfully."}

def update_station_capacity(session: Session, station_type: str, new_capacity: int):
    """Updates the capacity of a station."""
    from app.models import Station
    station = session.exec(select(Station).where(Station.type == station_type)).first()
    if station:
        station.capacity = new_capacity
        session.add(station)

@router.get("/machine-performance")
def get_machine_performance(session: Session = Depends(get_session)):
    """Returns real-time machine performance data."""
    from app.models import Machine, Station, Event
    from datetime import datetime, timedelta, timezone
    
    performance_data = {}
    
    # Get machine performance for each station type
    for station_type in ["washing", "drying", "folding"]:
        station = session.exec(select(Station).where(Station.type == station_type)).first()
        if not station:
            continue
            
        machines = session.exec(select(Machine).where(Machine.station_id == station.id)).all()
        if not machines:
            continue
            
        # Calculate average cycle time from recent events
        recent_events = session.exec(
            select(Event)
            .where(Event.to_status.like(f"Basket-%Finished-{station_type}"))
            .where(Event.timestamp >= datetime.now(timezone.utc) - timedelta(days=7))
        ).all()
        
        if recent_events:
            # Calculate average cycle time from events
            cycle_times = []
            for event in recent_events:
                try:
                    meta = json.loads(event.meta) if event.meta else {}
                    if 'machine_id' in meta:
                        machine = session.get(Machine, meta['machine_id'])
                        if machine and machine.cycle_time_seconds:
                            cycle_times.append(machine.cycle_time_seconds)
                except:
                    continue
            
            if cycle_times:
                avg_cycle_time = sum(cycle_times) / len(cycle_times)
                performance_data[station_type] = {
                    "average_cycle_time": round(avg_cycle_time),
                    "total_machines": len(machines),
                    "active_machines": len([m for m in machines if m.state == "running"]),
                    "idle_machines": len([m for m in machines if m.state == "idle"])
                }
    
    return performance_data

@router.get("/kpi-summary")
def get_kpi_summary(session: Session = Depends(get_session)):
    """Returns current KPI performance summary."""
    from app.queries.dashboard_queries import (
        get_retention_kpis, get_turnaround_kpi, get_pickup_kpi, 
        get_delivery_kpi, get_claim_rate_kpi, get_claims_resolution_kpi
    )
    
    try:
        return {
            "retention": get_retention_kpis(session),
            "turnaround": get_turnaround_kpi(session),
            "pickup": get_pickup_kpi(session),
            "delivery": get_delivery_kpi(session),
            "claim_rate": get_claim_rate_kpi(session),
            "claims_resolution": get_claims_resolution_kpi(session)
        }
    except Exception as e:
        return {"error": str(e)}


# --- Claim Management API ---

class ClaimUpdateRequest(BaseModel):
    action: Literal["rewash", "deny", "compensate", "compensate_rewash"]
    notes: Optional[str] = None
    amount: Optional[float] = Field(default=None, gt=0)

@router.post("/claims/{claim_id}/update", response_model=Claim)
def update_claim_status(
    claim_id: int,
    request: ClaimUpdateRequest,
    session: Session = Depends(get_session)
):
    """
    Handles administrative actions on a claim (deny, compensate, rewash).
    """
    claim = session.get(Claim, claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")

    order = session.get(Order, claim.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Associated order not found")

    admin_note = f"\n[Admin Note: {request.notes}]" if request.notes else ""

    if request.action == "deny":
        claim.status = "denied"
        claim.notes += admin_note
    
    elif request.action == "compensate":
        if not request.amount:
            raise HTTPException(status_code=400, detail="Amount is required for compensation.")
        claim.status = "resolved"
        claim.amount = request.amount
        claim.notes += admin_note

    elif request.action == "rewash":
        claim.status = "resolved"
        claim.notes += admin_note
        apply_transition(session, order, "Pretreat", meta={"reason": "Admin-triggered rewash", "claim_id": claim.id})

    elif request.action == "compensate_rewash":
        if not request.amount:
            raise HTTPException(status_code=400, detail="Amount is required for compensation.")
        claim.status = "resolved"
        claim.amount = request.amount
        claim.notes += admin_note
        apply_transition(session, order, "Pretreat", meta={"reason": "Admin-triggered compensate & rewash", "claim_id": claim.id})

    claim.resolved_at = datetime.now(timezone.utc)
    session.add(claim)
    session.commit()
    session.refresh(claim)
    
    return claim