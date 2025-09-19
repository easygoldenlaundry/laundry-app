# app/routes/admin_api.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict
from datetime import datetime, timezone

from app.db import get_session
from app.models import User, Station, Machine, Claim, Order, Setting
from app.services.state_machine import apply_transition
from app.auth import get_current_admin_user

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

# --- THIS IS THE FIX: New endpoint to update user permissions ---
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

    # Convert the list of strings to a single comma-separated string for DB storage
    user.allowed_stations = ",".join(request.allowed_stations)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user





# --- Settings API ---

@router.get("/settings", response_model=Dict[str, str])
def get_all_settings(session: Session = Depends(get_session)):
    """Retrieves all application settings as a key-value dictionary."""
    settings = session.exec(select(Setting)).all()
    return {s.key: s.value for s in settings}

class SettingsUpdateRequest(BaseModel):
    settings: Dict[str, str]

def reconcile_machines(session: Session, station_type: str, new_count: int, cycle_time: int):
    """Adds or removes machines for a station to match a new count."""
    station = session.exec(select(Station).where(Station.type == station_type)).first()
    if not station:
        return # Station might not exist in some environments

    current_machines = session.exec(select(Machine).where(Machine.station_id == station.id)).all()
    current_count = len(current_machines)
    diff = new_count - current_count

    if diff > 0:  # Add machines
        for _ in range(diff):
            new_machine = Machine(
                station_id=station.id,
                type=station.type.removesuffix('ing'),
                cycle_time_seconds=cycle_time
            )
            session.add(new_machine)
    elif diff < 0:  # Remove machines
        idle_machines = [m for m in current_machines if m.state == "idle"]
        num_to_remove = abs(diff)
        if len(idle_machines) < num_to_remove:
            # Not raising exception, just removing what we can to avoid blocking settings saves.
            # A more advanced implementation might queue this for later.
            num_to_remove = len(idle_machines)
        
        for i in range(num_to_remove):
            session.delete(idle_machines[i])

@router.post("/settings")
def update_settings(request: SettingsUpdateRequest, session: Session = Depends(get_session)):
    """Updates multiple settings at once and reconciles machine counts."""
    for key, value in request.settings.items():
        setting = session.get(Setting, key)
        if setting:
            setting.value = value
            session.add(setting)
        else:
            new_setting = Setting(key=key, value=value)
            session.add(new_setting)
    
    # After saving, reconcile machine counts based on new settings
    try:
        reconcile_machines(session, "washing", int(request.settings.get("washing_machine_count", 1)), int(request.settings.get("wash_cycle_time_seconds", 1800)))
        reconcile_machines(session, "drying", int(request.settings.get("drying_machine_count", 1)), int(request.settings.get("dry_cycle_time_seconds", 2400)))
        reconcile_machines(session, "folding", int(request.settings.get("folding_machine_count", 1)), int(request.settings.get("fold_cycle_time_seconds", 300)))
    except Exception as e:
        # Avoid crashing if a station doesn't exist yet
        print(f"Could not reconcile machines, possibly expected during initial setup: {e}")


    session.commit()
    return {"message": "Settings updated successfully."}


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