# app/routes/driver.py
import os
import uuid
import json
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from fastapi import (APIRouter, Depends, Form, HTTPException, Request, Response,
                     File, UploadFile, BackgroundTasks)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from pydantic import BaseModel

from app.db import get_session
from app.models import Bag, Image, Order, User, Setting, Driver
from app.auth import get_current_driver_user, get_current_hybrid_driver_user, get_current_hybrid_driver_user
from app.services.state_machine import apply_transition
from app.services.finance_calculator import create_finance_entries_for_order
from app.services.inventory_manager import deduct_stock_for_order
from app.config import DATA_ROOT

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# The main driver dashboard is now protected
@router.get("/driver", response_class=HTMLResponse, dependencies=[Depends(get_current_driver_user)])
async def get_driver_dashboard(request: Request):
    # The user object is added to the request state by the middleware
    return templates.TemplateResponse("driver.html", {"request": request, "user": request.state.user})


class OrderActionRequest(BaseModel):
    order_id: int

# All API endpoints are protected by the dependency
@router.post("/api/drivers/{user_id}/accept", response_model=Order, dependencies=[Depends(get_current_hybrid_driver_user)])
async def accept_order(user_id: int, request_data: OrderActionRequest, current_user: User = Depends(get_current_hybrid_driver_user), session: Session = Depends(get_session)):
    if user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")
    
    # Get the Driver record for this user
    driver = session.exec(select(Driver).where(Driver.user_id == current_user.id)).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found. Please contact admin.")
    
    order = session.get(Order, request_data.order_id)
    if not order: raise HTTPException(status_code=404, detail="Order not found")
    if order.assigned_driver_id is not None: raise HTTPException(status_code=409, detail="Order already assigned")
    
    try:
        order.assigned_driver_id = driver.id  # Use driver.id, not user_id
        
        # Generate pickup PIN if not already set
        if not order.pickup_pin:
            import secrets
            order.pickup_pin = str(secrets.randbelow(10000)).zfill(4)
        
        session.add(order)
        updated_order = apply_transition(session, order, "AssignedToDriver", user_id=user_id)
        return updated_order
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@router.post("/api/drivers/{user_id}/accept_delivery", response_model=Order, dependencies=[Depends(get_current_hybrid_driver_user)])
async def accept_delivery_job(user_id: int, request_data: OrderActionRequest, current_user: User = Depends(get_current_hybrid_driver_user), session: Session = Depends(get_session)):
    if user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")
    
    # Get the Driver record for this user
    driver = session.exec(select(Driver).where(Driver.user_id == current_user.id)).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found. Please contact admin.")
    
    order = session.get(Order, request_data.order_id)
    if not order: raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "OutForDelivery": raise HTTPException(status_code=400, detail="Order is not ready for delivery")
    if order.assigned_driver_id is not None: raise HTTPException(status_code=409, detail="Delivery job already assigned")
    
    order.assigned_driver_id = driver.id  # Use driver.id, not user_id
    session.add(order)
    session.commit()
    session.refresh(order)
    
    from app.sockets import broadcast_order_update
    import asyncio
    try:
        asyncio.run(broadcast_order_update(order))
    except RuntimeError:
        loop = asyncio.get_event_loop()
        loop.create_task(broadcast_order_update(order))

    return order

@router.post("/api/drivers/{user_id}/picked_up", response_model=Order, dependencies=[Depends(get_current_hybrid_driver_user)])
async def picked_up_order(
    user_id: int,
    order_id: int = Form(...),
    pin: str = Form(...),
    load_count: int = Form(...),
    proof_photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_hybrid_driver_user),
    session: Session = Depends(get_session)
):
    if user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")
    order = session.get(Order, order_id)
    if not order: raise HTTPException(status_code=404, detail="Order not found")
    
    valid_pins = {order.pickup_pin, order.customer_phone[-4:]}
    if pin not in valid_pins:
        raise HTTPException(status_code=403, detail="Invalid PIN provided.")

    order.confirmed_load_count = load_count
    session.add(order)

    meta = {"pickup_pin_used": pin, "confirmed_load_count": load_count}
    if proof_photo:
        # ... file saving logic ...
        pass
    updated_order = apply_transition(session, order, "PickedUp", user_id=user_id, meta=meta)
    return updated_order

@router.post("/api/drivers/{user_id}/delivered_to_hub", response_model=Order, dependencies=[Depends(get_current_hybrid_driver_user)])
async def delivered_to_hub_order(user_id: int, order_id: int = Form(...), hub_qr_code: str = Form(...), proof_photo: Optional[UploadFile] = File(None), current_user: User = Depends(get_current_hybrid_driver_user), session: Session = Depends(get_session)):
    if user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")
    order = session.get(Order, order_id)
    if not order: raise HTTPException(status_code=404, detail="Order not found")
    
    correct_qr_code_setting = session.get(Setting, "driver_hub_delivery_qr")
    if not correct_qr_code_setting or hub_qr_code.strip() != correct_qr_code_setting.value:
        raise HTTPException(status_code=403, detail="Invalid Hub Delivery QR Code.")

    meta = {}
    if proof_photo:
        # ... file saving logic ...
        pass
    updated_order = apply_transition(session, order, "DeliveredToHub", user_id=user_id, meta=meta)
    return updated_order

@router.post("/api/drivers/{user_id}/pickup_from_hub", response_model=Order, dependencies=[Depends(get_current_hybrid_driver_user)])
async def pickup_from_hub(user_id: int, order_id: int = Form(...), hub_qr_code: str = Form(...), current_user: User = Depends(get_current_hybrid_driver_user), session: Session = Depends(get_session)):
    if user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")
    order = session.get(Order, order_id)
    if not order: raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "OutForDelivery": raise HTTPException(status_code=400, detail="Order not in correct state for hub pickup")
    
    correct_qr_code_setting = session.get(Setting, "driver_hub_pickup_qr")
    if not correct_qr_code_setting or hub_qr_code.strip() != correct_qr_code_setting.value:
        raise HTTPException(status_code=403, detail="Invalid Hub Pickup QR Code.")

    meta = {"hub_pickup_qr_used": hub_qr_code.strip()}
    updated_order = apply_transition(session, order, "OnRouteToCustomer", user_id=user_id, meta=meta)
    return updated_order

@router.post("/api/drivers/{user_id}/delivered", response_model=Order, dependencies=[Depends(get_current_hybrid_driver_user)])
async def delivered_order(
    user_id: int,
    background_tasks: BackgroundTasks,
    order_id: int = Form(...),
    pin: str = Form(...),
    proof_photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_hybrid_driver_user),
    session: Session = Depends(get_session)
):
    if user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")
    order = session.get(Order, order_id)
    if not order: raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "OnRouteToCustomer":
        raise HTTPException(status_code=400, detail=f"Order is not on route. Current status: {order.status}")

    valid_pins = {order.delivery_pin, order.customer_phone[-4:]}
    if pin not in valid_pins:
        raise HTTPException(status_code=403, detail="Invalid delivery confirmation PIN.")

    meta = {"delivery_confirmation_code_used": pin}
    if proof_photo:
        # ... file saving logic ...
        pass
    updated_order = apply_transition(session, order, "Delivered", user_id=user_id, meta=meta)

    background_tasks.add_task(create_finance_entries_for_order, order_id=order.id, session=session)
    background_tasks.add_task(deduct_stock_for_order, order_id=order.id, session=session)
    
    return updated_order

@router.get("/api/drivers/available_orders", response_model=list[Order], dependencies=[Depends(get_current_hybrid_driver_user)])
async def get_available_orders(session: Session = Depends(get_session)):
    available_orders = session.exec(
        select(Order).where(Order.status == "Created", Order.dispatch_method == "inhouse")
    ).all()
    return available_orders

@router.get("/api/drivers/available_deliveries", response_model=list[Order], dependencies=[Depends(get_current_hybrid_driver_user)])
async def get_available_deliveries(session: Session = Depends(get_session)):
    available_deliveries = session.exec(
        select(Order).where(Order.status == "OutForDelivery", Order.assigned_driver_id == None)
    ).all()
    return available_deliveries

@router.get("/api/drivers/my_jobs", response_model=List[Order], dependencies=[Depends(get_current_hybrid_driver_user)])
async def get_my_jobs(current_user: User = Depends(get_current_hybrid_driver_user), session: Session = Depends(get_session)):
    """Returns all active jobs assigned to the current driver."""
    # Get the Driver record for this user
    driver = session.exec(select(Driver).where(Driver.user_id == current_user.id)).first()
    if not driver:
        return []  # Return empty list if no driver profile exists

    active_driver_statuses = [
        "AssignedToDriver",
        "PickedUp",
        "OutForDelivery",
        "OnRouteToCustomer"
    ]
    my_jobs = session.exec(
        select(Order)
        .where(Order.assigned_driver_id == driver.id, Order.status.in_(active_driver_statuses))
    ).all()
    return my_jobs


# Mobile API endpoints (aliased versions for Android app compatibility)
@router.get("/api/drivers/mobile/available_orders", response_model=list[Order], dependencies=[Depends(get_current_hybrid_driver_user)])
async def get_mobile_available_orders(session: Session = Depends(get_session)):
    """Mobile endpoint for available orders."""
    available_orders = session.exec(
        select(Order).where(Order.status == "Created", Order.dispatch_method == "inhouse")
    ).all()
    return available_orders

@router.get("/api/drivers/mobile/available_deliveries", response_model=list[Order], dependencies=[Depends(get_current_hybrid_driver_user)])
async def get_mobile_available_deliveries(session: Session = Depends(get_session)):
    """Mobile endpoint for available deliveries."""
    available_deliveries = session.exec(
        select(Order).where(Order.status == "OutForDelivery", Order.assigned_driver_id == None)
    ).all()
    return available_deliveries

@router.get("/api/drivers/mobile/my_jobs", response_model=List[Order], dependencies=[Depends(get_current_hybrid_driver_user)])
async def get_mobile_my_jobs(current_user: User = Depends(get_current_hybrid_driver_user), session: Session = Depends(get_session)):
    """Mobile endpoint for driver's active jobs."""
    # Get the Driver record for this user
    driver = session.exec(select(Driver).where(Driver.user_id == current_user.id)).first()
    if not driver:
        return []  # Return empty list if no driver profile exists

    active_driver_statuses = [
        "AssignedToDriver",
        "PickedUp",
        "OutForDelivery",
        "OnRouteToCustomer"
    ]
    my_jobs = session.exec(
        select(Order)
        .where(Order.assigned_driver_id == driver.id, Order.status.in_(active_driver_statuses))
    ).all()
    return my_jobs

@router.post("/api/drivers/mobile/accept", response_model=Order, dependencies=[Depends(get_current_hybrid_driver_user)])
async def mobile_accept_order(request_data: OrderActionRequest, current_user: User = Depends(get_current_hybrid_driver_user), session: Session = Depends(get_session)):
    """Mobile endpoint to accept an order for pickup."""
    # Get the Driver record for this user
    driver = session.exec(select(Driver).where(Driver.user_id == current_user.id)).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found. Please contact admin.")

    order = session.get(Order, request_data.order_id)
    if not order: raise HTTPException(status_code=404, detail="Order not found")
    if order.assigned_driver_id is not None: raise HTTPException(status_code=409, detail="Order already assigned")

    try:
        order.assigned_driver_id = driver.id  # Use driver.id, not user_id

        # Generate pickup PIN if not already set
        if not order.pickup_pin:
            import secrets
            order.pickup_pin = str(secrets.randbelow(10000)).zfill(4)

        # Set status manually like apply_transition does
        from datetime import datetime, timezone
        from app.models import Event
        now = datetime.now(timezone.utc)
        original_status = order.status
        order.status = "AssignedToDriver"
        order.updated_at = now

        # Create Event record like apply_transition does
        event = Event(
            order_id=order.id,
            from_status=original_status,
            to_status="AssignedToDriver",
            user_id=current_user.id,
            meta=None,
        )
        session.add(event)
        session.add(order)
        session.commit()
        session.refresh(order)

        # Broadcast update (same pattern as web delivery accept)
        from app.sockets import broadcast_order_update
        import asyncio
        try:
            asyncio.run(broadcast_order_update(order))
        except RuntimeError:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(broadcast_order_update(order))

        return order
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@router.post("/api/drivers/mobile/accept_delivery", response_model=Order, dependencies=[Depends(get_current_hybrid_driver_user)])
async def mobile_accept_delivery_job(request_data: OrderActionRequest, current_user: User = Depends(get_current_hybrid_driver_user), session: Session = Depends(get_session)):
    """Mobile endpoint to accept a delivery job."""
    # Get the Driver record for this user
    driver = session.exec(select(Driver).where(Driver.user_id == current_user.id)).first()
    if not driver:
        raise HTTPException(status_code=404, detail="Driver profile not found. Please contact admin.")

    order = session.get(Order, request_data.order_id)
    if not order: raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "OutForDelivery": raise HTTPException(status_code=400, detail="Order is not ready for delivery")
    if order.assigned_driver_id is not None: raise HTTPException(status_code=409, detail="Delivery job already assigned")

    order.assigned_driver_id = driver.id  # Use driver.id, not user_id
    session.add(order)
    session.commit()
    session.refresh(order)

    # TODO: Re-enable socket broadcasting after fixing async issues
    # from app.sockets import broadcast_order_update
    # import asyncio
    # try:
    #     loop = asyncio.get_event_loop()
    #     if loop.is_running():
    #         loop.create_task(broadcast_order_update(order))
    # except RuntimeError:
    #     pass

    return order

@router.post("/api/drivers/mobile/picked_up", response_model=Order, dependencies=[Depends(get_current_hybrid_driver_user)])
async def mobile_picked_up_order(
    order_id: int = Form(...),
    pin: str = Form(...),
    load_count: int = Form(...),
    proof_photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_hybrid_driver_user),
    session: Session = Depends(get_session)
):
    """Mobile endpoint for order pickup confirmation."""
    order = session.get(Order, order_id)
    if not order: raise HTTPException(status_code=404, detail="Order not found")

    valid_pins = {order.pickup_pin, order.customer_phone[-4:]}
    if pin not in valid_pins:
        raise HTTPException(status_code=403, detail="Invalid PIN provided.")

    order.confirmed_load_count = load_count
    session.add(order)

    meta = {"pickup_pin_used": pin, "confirmed_load_count": load_count}
    if proof_photo:
        # ... file saving logic ...
        pass
    updated_order = apply_transition(session, order, "PickedUp", user_id=current_user.id, meta=meta)
    return updated_order

@router.post("/api/drivers/mobile/delivered_to_hub", response_model=Order, dependencies=[Depends(get_current_hybrid_driver_user)])
async def mobile_delivered_to_hub_order(order_id: int = Form(...), hub_qr_code: str = Form(...), proof_photo: Optional[UploadFile] = File(None), current_user: User = Depends(get_current_hybrid_driver_user), session: Session = Depends(get_session)):
    """Mobile endpoint for delivering order to hub."""
    order = session.get(Order, order_id)
    if not order: raise HTTPException(status_code=404, detail="Order not found")

    correct_qr_code_setting = session.get(Setting, "driver_hub_delivery_qr")
    if not correct_qr_code_setting or hub_qr_code.strip() != correct_qr_code_setting.value:
        raise HTTPException(status_code=403, detail="Invalid Hub Delivery QR Code.")

    meta = {}
    if proof_photo:
        # ... file saving logic ...
        pass
    updated_order = apply_transition(session, order, "DeliveredToHub", user_id=current_user.id, meta=meta)
    return updated_order

@router.post("/api/drivers/mobile/pickup_from_hub", response_model=Order, dependencies=[Depends(get_current_hybrid_driver_user)])
async def mobile_pickup_from_hub(order_id: int = Form(...), hub_qr_code: str = Form(...), current_user: User = Depends(get_current_hybrid_driver_user), session: Session = Depends(get_session)):
    """Mobile endpoint for picking up order from hub for delivery."""
    order = session.get(Order, order_id)
    if not order: raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "OutForDelivery": raise HTTPException(status_code=400, detail="Order not in correct state for hub pickup")

    correct_qr_code_setting = session.get(Setting, "driver_hub_pickup_qr")
    if not correct_qr_code_setting or hub_qr_code.strip() != correct_qr_code_setting.value:
        raise HTTPException(status_code=403, detail="Invalid Hub Pickup QR Code.")

    meta = {"hub_pickup_qr_used": hub_qr_code.strip()}
    updated_order = apply_transition(session, order, "OnRouteToCustomer", user_id=current_user.id, meta=meta)
    return updated_order

@router.post("/api/drivers/mobile/delivered", response_model=Order, dependencies=[Depends(get_current_hybrid_driver_user)])
async def mobile_delivered_order(
    background_tasks: BackgroundTasks,
    order_id: int = Form(...),
    pin: str = Form(...),
    proof_photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_hybrid_driver_user),
    session: Session = Depends(get_session)
):
    """Mobile endpoint for final delivery completion."""
    order = session.get(Order, order_id)
    if not order: raise HTTPException(status_code=404, detail="Order not found")
    if order.status != "OnRouteToCustomer":
        raise HTTPException(status_code=400, detail=f"Order is not on route. Current status: {order.status}")

    valid_pins = {order.delivery_pin, order.customer_phone[-4:]}
    if pin not in valid_pins:
        raise HTTPException(status_code=403, detail="Invalid delivery confirmation PIN.")

    meta = {"delivery_confirmation_code_used": pin}
    if proof_photo:
        # ... file saving logic ...
        pass
    updated_order = apply_transition(session, order, "Delivered", user_id=current_user.id, meta=meta)

    background_tasks.add_task(create_finance_entries_for_order, order_id=order.id, session=session)
    background_tasks.add_task(deduct_stock_for_order, order_id=order.id, session=session)

    return updated_order

# Additional mobile endpoints with user_id in path (as expected by Android app)

@router.post("/api/drivers/mobile/{user_id}/accept")
async def mobile_accept_order_with_user_id(user_id: int, request_data: OrderActionRequest, current_user: User = Depends(get_current_hybrid_driver_user), session: Session = Depends(get_session)):
    """Mobile endpoint to accept an order for pickup (with user_id in path)."""
    if user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")
    order = mobile_accept_order(request_data, current_user, session)
    return {"message": "Job accepted successfully", "order": order}

@router.post("/api/drivers/mobile/{user_id}/accept_delivery")
async def mobile_accept_delivery_job_with_user_id(user_id: int, request_data: OrderActionRequest, current_user: User = Depends(get_current_hybrid_driver_user), session: Session = Depends(get_session)):
    """Mobile endpoint to accept a delivery job (with user_id in path)."""
    if user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")
    order = mobile_accept_delivery_job(request_data, current_user, session)
    return {"message": "Job accepted successfully", "order": order}

@router.post("/api/drivers/mobile/{user_id}/picked_up")
async def mobile_picked_up_order_with_user_id(
    user_id: int,
    order_id: int = Form(...),
    pin: str = Form(...),
    load_count: int = Form(...),
    proof_photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_hybrid_driver_user),
    session: Session = Depends(get_session)
):
    """Mobile endpoint for order pickup confirmation (with user_id in path)."""
    if user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")
    order = mobile_picked_up_order(order_id, pin, load_count, proof_photo, current_user, session)
    return {"message": "Pickup completed successfully", "order": order}

@router.post("/api/drivers/mobile/{user_id}/delivered_to_hub")
async def mobile_delivered_to_hub_order_with_user_id(
    user_id: int,
    order_id: int = Form(...),
    hub_qr_code: str = Form(...),
    proof_photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_hybrid_driver_user),
    session: Session = Depends(get_session)
):
    """Mobile endpoint for delivering order to hub (with user_id in path)."""
    if user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")
    order = mobile_delivered_to_hub_order(order_id, hub_qr_code, proof_photo, current_user, session)
    return {"message": "Delivered to hub successfully", "order": order}

@router.post("/api/drivers/mobile/{user_id}/pickup_from_hub")
async def mobile_pickup_from_hub_with_user_id(
    user_id: int,
    order_id: int = Form(...),
    hub_qr_code: str = Form(...),
    current_user: User = Depends(get_current_hybrid_driver_user),
    session: Session = Depends(get_session)
):
    """Mobile endpoint for picking up order from hub for delivery (with user_id in path)."""
    if user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")
    order = mobile_pickup_from_hub(order_id, hub_qr_code, current_user, session)
    return {"message": "Picked up from hub successfully", "order": order}

@router.post("/api/drivers/mobile/{user_id}/delivered")
async def mobile_delivered_order_with_user_id(
    user_id: int,
    background_tasks: BackgroundTasks,
    order_id: int = Form(...),
    pin: str = Form(...),
    proof_photo: Optional[UploadFile] = File(None),
    current_user: User = Depends(get_current_hybrid_driver_user),
    session: Session = Depends(get_session)
):
    """Mobile endpoint for final delivery completion (with user_id in path)."""
    if user_id != current_user.id: raise HTTPException(status_code=403, detail="Forbidden")
    order = mobile_delivered_order(background_tasks, order_id, pin, proof_photo, current_user, session)
    return {"message": "Delivery completed successfully", "order": order}