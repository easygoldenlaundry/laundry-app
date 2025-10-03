# app/routes/location.py
import logging
import math
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.auth import get_current_driver_user
from app.models import User, Order, Driver
from app.sockets import broadcast_driver_location_update
from app.services.helpers import haversine_distance

router = APIRouter(prefix="/api/driver", tags=["Driver Location"])

class LocationUpdateRequest(BaseModel):
    lat: float
    lon: float

HUB_COORDINATES = (-26.1952, 28.0341) # Lat, Lon for the hub (e.g., Johannesburg)

@router.post("/location", status_code=204)
async def update_driver_location(
    location_data: LocationUpdateRequest,
    driver_user: User = Depends(get_current_driver_user),
    session: Session = Depends(get_session)
):
    """Receives location updates from a driver and broadcasts progress to the customer."""
    
    driver_profile = session.exec(select(Driver).where(Driver.user_id == driver_user.id)).first()
    if not driver_profile:
        return
        
    driver_profile.last_location = f"{location_data.lat},{location_data.lon}"
    session.add(driver_profile)

    active_statuses = ["AssignedToDriver", "OnRouteToCustomer"]
    order = session.exec(
        select(Order).where(Order.assigned_driver_id == driver_user.id, Order.status.in_(active_statuses))
    ).first()

    if not order:
        session.commit()
        return

    if order.status == "AssignedToDriver":
        start_lat, start_lon = order.initial_driver_lat, order.initial_driver_lon
        dest_lat, dest_lon = order.pickup_lat, order.pickup_lon
    else: # OnRouteToCustomer
        start_lat, start_lon = HUB_COORDINATES
        dest_lat, dest_lon = order.delivery_lat, order.delivery_lon

    if order.status == "AssignedToDriver" and not order.initial_driver_lat:
        order.initial_driver_lat = location_data.lat
        order.initial_driver_lon = location_data.lon
        start_lat, start_lon = location_data.lat, location_data.lon
        session.add(order)
        
    session.commit()

    if not all([start_lat, start_lon, dest_lat, dest_lon]):
        logging.warning(f"Order {order.id} is missing coordinates for progress calculation.")
        return

    initial_distance = haversine_distance(start_lat, start_lon, dest_lat, dest_lon)
    current_distance = haversine_distance(location_data.lat, location_data.lon, dest_lat, dest_lon)
    
    progress = 0
    if initial_distance > 0.05:
        progress = max(0, min(100, (1 - (current_distance / initial_distance)) * 100))

    avg_speed_kph = 35
    eta_minutes = math.ceil((current_distance / avg_speed_kph) * 60) if current_distance < float('inf') else 99

    await broadcast_driver_location_update(order.id, {
        "progress": progress,
        "eta_minutes": eta_minutes
    })