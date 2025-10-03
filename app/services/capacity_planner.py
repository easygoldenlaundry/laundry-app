# app/services/capacity_planner.py
import math
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any
from sqlmodel import Session, select, func

from app.models import Order, Setting

# These statuses represent orders that are occupying or will soon occupy a machine.
POST_PICKUP_STATUSES = [
    "PickedUp", "DeliveredToHub", "AtHub", "Imaging", "Processing"
]

def get_settings_as_dict(session: Session) -> Dict[str, float]:
    """Fetches all settings and casts numeric ones to float."""
    settings_db = session.exec(select(Setting)).all()
    settings = {}
    for s in settings_db:
        try:
            settings[s.key] = float(s.value)
        except (ValueError, TypeError):
            settings[s.key] = s.value
    return settings

def calculate_bottleneck(settings: Dict[str, float]) -> Dict[str, Any]:
    """
    Identifies the slowest machine-based stage in the production pipeline.
    Returns the bottleneck's name, throughput per machine, and total throughput.
    """
    stages = {
        'washing': settings.get('wash_cycle_time_seconds', 1800) / settings.get('washing_machine_count', 1),
        'drying': settings.get('dry_cycle_time_seconds', 7200) / settings.get('drying_machine_count', 1),
        'folding': settings.get('fold_cycle_time_seconds', 300) / settings.get('folding_machine_count', 1),
    }
    
    bottleneck_stage = max(stages, key=stages.get)
    time_per_load_seconds = stages[bottleneck_stage]
    
    return {
        "name": bottleneck_stage,
        "time_increment_seconds": time_per_load_seconds,
        "num_machines": settings.get(f"{bottleneck_stage}_machine_count", 1)
    }

def get_current_workload(session: Session) -> int:
    """
    Calculates the current workload.
    - Assumes 3 loads for each order awaiting pickup.
    - Uses the driver-confirmed load count for orders in processing.
    """
    # Workload for orders awaiting pickup (assume 3 loads each)
    pre_pickup_statuses = ["Created", "AssignedToDriver"]
    pre_pickup_order_count = session.exec(
        select(func.count(Order.id))
        .where(Order.status.in_(pre_pickup_statuses))
    ).one()
    pre_pickup_workload = pre_pickup_order_count * 3

    # Workload for orders already in the physical pipeline (use confirmed count)
    post_pickup_workload = session.exec(
        select(func.sum(Order.confirmed_load_count))
        .where(
            Order.status.in_(POST_PICKUP_STATUSES),
            Order.confirmed_load_count != None
        )
    ).one_or_none() or 0

    return pre_pickup_workload + post_pickup_workload

def get_base_turnaround_seconds(settings: Dict[str, float]) -> float:
    """Calculates the minimum processing time for a single load through the entire system."""
    return (
        settings.get("wash_cycle_time_seconds", 1800) +
        settings.get("dry_cycle_time_seconds", 7200) +
        settings.get("fold_cycle_time_seconds", 300) +
        settings.get("imaging_time_seconds_per_load", 300) +
        settings.get("qa_time_seconds_per_load", 300) +
        settings.get("packaging_time_seconds_per_load", 180)
    )

def generate_availability_slots(session: Session) -> Dict[str, Any]:
    """
    Calculates the single earliest available slot based on current system workload
    and returns it with fixed pricing options.
    """
    settings = get_settings_as_dict(session)
    bottleneck = calculate_bottleneck(settings)
    current_workload_loads = get_current_workload(session)
    base_turnaround_seconds = get_base_turnaround_seconds(settings)
    
    workload_delay_seconds = current_workload_loads * bottleneck["time_increment_seconds"]
    
    now = datetime.now(timezone.utc)
    first_available_time = now + timedelta(seconds=(base_turnaround_seconds + workload_delay_seconds))
    turnaround_hours = (first_available_time - now).total_seconds() / 3600

    standard_price = settings.get("standard_price_per_load", 210.0)
    wait_and_save_price = settings.get("wait_and_save_price_per_load", 150.0)

    earliest_slot = {
        "timestamp": first_available_time.isoformat(),
        "turnaround_hours": round(max(0, turnaround_hours), 1),
        "price_per_load": round(standard_price, 2)
    }

    return {
        "slot": earliest_slot,
        "wait_and_save_price": round(wait_and_save_price, 2)
    }