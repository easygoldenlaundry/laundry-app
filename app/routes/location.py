# app/routes/location.py
import logging
import math
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.auth import get_current_hybrid_driver_user
from app.models import User, Order, Driver
from app.sockets import broadcast_driver_location_update
from app.services.helpers import haversine_distance

router = APIRouter(prefix="/api/driver", tags=["Driver Location"])

class LocationUpdateRequest(BaseModel):
    lat: float
    lon: float

# Hub location (Latitude, Longitude). In a real app, this would come from the DB.
HUB_COORDINATES = (-26.1952, 28.0341)

# Mobile app location update request model
class MobileLocationUpdateRequest(BaseModel):
    lat: float
    lon: float
    order_id: Optional[int] = None  # Optional for when driver has active job 

@router.post("/location", status_code=204)
async def update_driver_location(
    location_data: LocationUpdateRequest,
    driver_user: User = Depends(get_current_hybrid_driver_user),
    session: Session = Depends(get_session)
):
    """
    Receives location updates from the driver's device (web or future native app).
    Calculates progress and ETA, then broadcasts updates to the customer.
    """
    
    driver_profile = session.exec(select(Driver).where(Driver.user_id == driver_user.id)).first()
    if not driver_profile:
        return # Silently fail if no driver profile exists
        
    driver_profile.last_location = f"{location_data.lat},{location_data.lon}"
    driver_profile.last_seen = datetime.now(timezone.utc)
    session.add(driver_profile)

    # Find the driver's active job
    active_statuses = ["AssignedToDriver", "OnRouteToCustomer"]
    order = session.exec(
        select(Order).where(Order.assigned_driver_id == driver_user.id, Order.status.in_(active_statuses))
    ).first()

    # If no active job, just update driver's last seen and exit
    if not order:
        session.commit()
        return

    # Determine start and destination coordinates based on order status
    if order.status == "AssignedToDriver":
        # On first update, capture the driver's starting position for the trip
        if not order.initial_driver_lat or not order.initial_driver_lon:
            order.initial_driver_lat = location_data.lat
            order.initial_driver_lon = location_data.lon
        
        start_lat, start_lon = order.initial_driver_lat, order.initial_driver_lon
        dest_lat, dest_lon = order.pickup_lat, order.pickup_lon

    else: # OnRouteToCustomer
        start_lat, start_lon = HUB_COORDINATES
        dest_lat, dest_lon = order.delivery_lat, order.delivery_lon
        
    session.add(order)
    session.commit()

    # Calculate progress and ETA
    if not all([start_lat, start_lon, dest_lat, dest_lon]):
        logging.warning(f"Order {order.id} is missing coordinates for progress calculation.")
        return

    initial_distance = haversine_distance(start_lat, start_lon, dest_lat, dest_lon)
    current_distance = haversine_distance(location_data.lat, location_data.lon, dest_lat, dest_lon)
    
    progress = 0
    if initial_distance > 0.05: # Avoid division by zero if start/end are too close
        progress = max(0, min(100, (1 - (current_distance / initial_distance)) * 100))

    avg_speed_kph = 35 # Static average speed in km/h
    eta_minutes = math.ceil((current_distance / avg_speed_kph) * 60) if current_distance < float('inf') else 99

    # Broadcast the update to the customer
    await broadcast_driver_location_update(order.id, {
        "progress": round(progress, 2),
        "eta_minutes": eta_minutes
    })

# --- MOBILE APP ENDPOINTS ---

@router.post("/api/driver/mobile/location", status_code=200)
async def mobile_update_driver_location(
    location_data: MobileLocationUpdateRequest,
    driver_user: User = Depends(get_current_hybrid_driver_user),
    session: Session = Depends(get_session)
):
    """
    Mobile app endpoint for driver location updates.
    Calculates progress and ETA, then broadcasts updates to the customer.
    Returns current ETA information for the driver's active job.
    """
    from app.models import Driver

    driver_profile = session.exec(select(Driver).where(Driver.user_id == driver_user.id)).first()
    if not driver_profile:
        return {"error": "Driver profile not found"}

    driver_profile.last_location = f"{location_data.lat},{location_data.lon}"
    driver_profile.last_seen = datetime.now(timezone.utc)
    session.add(driver_profile)

    # Find the driver's active job
    active_statuses = ["AssignedToDriver", "OnRouteToCustomer"]
    order = session.exec(
        select(Order).where(Order.assigned_driver_id == driver_user.id, Order.status.in_(active_statuses))
    ).first()

    # If no active job, just update driver's last seen
    if not order:
        session.commit()
        return {"message": "Location updated", "has_active_job": False}

    # Determine start and destination coordinates based on order status
    if order.status == "AssignedToDriver":
        # On first update, capture the driver's starting position for the trip
        if not order.initial_driver_lat or not order.initial_driver_lon:
            order.initial_driver_lat = location_data.lat
            order.initial_driver_lon = location_data.lon

        start_lat, start_lon = order.initial_driver_lat, order.initial_driver_lon
        dest_lat, dest_lon = order.pickup_lat, order.pickup_lon

    else: # OnRouteToCustomer
        start_lat, start_lon = HUB_COORDINATES
        dest_lat, dest_lon = order.delivery_lat, order.delivery_lon

    session.add(order)
    session.commit()

    # Calculate progress and ETA if coordinates are available
    eta_info = {"has_active_job": True, "order_id": order.id, "status": order.status}

    if all([start_lat, start_lon, dest_lat, dest_lon]):
        initial_distance = haversine_distance(start_lat, start_lon, dest_lat, dest_lon)
        current_distance = haversine_distance(location_data.lat, location_data.lon, dest_lat, dest_lon)

        progress = 0
        if initial_distance > 0.05: # Avoid division by zero if start/end are too close
            progress = max(0, min(100, (1 - (current_distance / initial_distance)) * 100))

        avg_speed_kph = 35 # Static average speed in km/h
        eta_minutes = math.ceil((current_distance / avg_speed_kph) * 60) if current_distance < float('inf') else 99

        eta_info.update({
            "progress": round(progress, 2),
            "eta_minutes": eta_minutes,
            "current_distance_km": round(current_distance, 2),
            "destination_type": "pickup" if order.status == "AssignedToDriver" else "delivery"
        })

        # Broadcast the update to the customer
        await broadcast_driver_location_update(order.id, {
            "progress": round(progress, 2),
            "eta_minutes": eta_minutes
        })
    else:
        eta_info.update({
            "progress": 0,
            "eta_minutes": None,
            "error": "Missing coordinates for ETA calculation"
        })

    return eta_info

@router.get("/api/orders/mobile/{order_id}/eta")
async def get_mobile_order_eta(
    order_id: int,
    tracking_token: str,
    session: Session = Depends(get_session)
):
    """
    Mobile app endpoint to get current ETA information for an order.
    Requires tracking token for security (customers can get this from their order).
    """
    from app.models import Order

    # Verify the tracking token matches the order
    order = session.exec(
        select(Order).where(Order.id == order_id, Order.tracking_token == tracking_token)
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found or invalid tracking token")

    eta_info = {
        "order_id": order.id,
        "status": order.status,
        "has_driver_assigned": order.assigned_driver_id is not None
    }

    # Only provide ETA if driver is en route
    if order.status in ["AssignedToDriver", "OnRouteToCustomer"] and order.assigned_driver_id:
        from app.models import Driver
        driver = session.get(Driver, order.assigned_driver_id)

        if driver and driver.last_location:
            try:
                driver_lat, driver_lon = map(float, driver.last_location.split(','))

                # Determine destination based on order status
                if order.status == "AssignedToDriver":
                    dest_lat, dest_lon = order.pickup_lat, order.pickup_lon
                else:  # OnRouteToCustomer
                    dest_lat, dest_lon = order.delivery_lat, order.delivery_lon

                if all([driver_lat, driver_lon, dest_lat, dest_lon]):
                    current_distance = haversine_distance(driver_lat, driver_lon, dest_lat, dest_lon)
                    avg_speed_kph = 35
                    eta_minutes = math.ceil((current_distance / avg_speed_kph) * 60) if current_distance < float('inf') else 99

                    eta_info.update({
                        "eta_minutes": eta_minutes,
                        "driver_distance_km": round(current_distance, 2),
                        "last_location_update": driver.last_seen.isoformat() if driver.last_seen else None
                    })
                else:
                    eta_info["error"] = "Driver location or destination coordinates missing"

            except (ValueError, AttributeError) as e:
                eta_info["error"] = "Unable to calculate ETA from driver location"
        else:
            eta_info["error"] = "Driver location not available"
    else:
        eta_info["message"] = "No active driver assignment for ETA calculation"

    return eta_info