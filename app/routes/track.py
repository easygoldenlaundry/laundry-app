# app/routes/track.py
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Order, Image, Event

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# --- NEW: Centralized Timeline Definition ---
# This represents the visual steps on the timeline bar.
TIMELINE_STEPS = [
    {'id': 'Booked', 'label': 'Booked', 'icon': 'fas fa-file-alt'},
    {'id': 'PickedUp', 'label': 'Picked Up', 'icon': 'fas fa-truck-pickup'},
    {'id': 'AtHub', 'label': 'At Hub', 'icon': 'fas fa-warehouse'},
    {'id': 'Imaging', 'label': 'Imaging', 'icon': 'fas fa-camera'},
    {'id': 'Pretreat', 'label': 'Pretreat', 'icon': 'fas fa-spray-can'},
    {'id': 'Washing', 'label': 'Washing', 'icon': 'fas fa-tint'},
    {'id': 'Drying', 'label': 'Drying', 'icon': 'fas fa-wind'},
    {'id': 'Folding', 'label': 'Folding', 'icon': 'fas fa-tshirt'},
    {'id': 'QA', 'label': 'QA', 'icon': 'fas fa-clipboard-check'},
    {'id': 'Ready', 'label': 'Ready', 'icon': 'fas fa-box-open'},
    {'id': 'OnTheWay', 'label': 'On The Way', 'icon': 'fas fa-truck-fast'},
    {'id': 'Delivered', 'label': 'Delivered', 'icon': 'fas fa-home'},
]

# Map internal order statuses to the timeline step IDs. Some statuses map to the same visual step.
STATUS_TO_TIMELINE_ID = {
    "Created": "Booked",
    "AssignedToDriver": "Booked",
    "PickedUp": "PickedUp",
    "DeliveredToHub": "AtHub",
    "Imaging": "Imaging",
    "Processing": "Processing", # Special case for baskets
    "QA": "QA",
    "ReadyForDelivery": "Ready",
    "OutForDelivery": "OnTheWay",
    "OnRouteToCustomer": "OnTheWay",
    "Delivered": "Delivered",
    "Closed": "Delivered"
}

# Basket statuses map directly to timeline IDs
BASKET_STATUS_TO_TIMELINE_ID = {
    "Pretreat": "Pretreat",
    "Washing": "Washing",
    "Drying": "Drying",
    "Folding": "Folding",
    "QA": "QA"
}

@router.get("/track/{tracking_token}", response_class=HTMLResponse)
async def track_order_page(
    request: Request,
    tracking_token: str,
    session: Session = Depends(get_session)
):
    """Serves the customer-facing order tracking page."""
    
    order = session.exec(
        select(Order)
        .where(Order.tracking_token == tracking_token)
        .options(selectinload(Order.baskets)) # Eager load baskets
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    images = session.exec(
        select(Image).where(Image.order_id == order.id, Image.image_type == "item_scan")
    ).all()
    
    all_events = session.exec(
        select(Event).where(Event.order_id == order.id).order_by(Event.timestamp.asc())
    ).all()

    key_events = [e for e in all_events if not e.to_status.startswith("Basket-")]

    formatted_sla = order.sla_deadline.strftime('%A, %b %d at %H:%M') if order.sla_deadline else ""
    
    # --- REWRITTEN: New unified timeline logic ---
    timeline_step_ids = [step['id'] for step in TIMELINE_STEPS]
    total_steps = len(timeline_step_ids)

    markers = []
    overall_progress_percent = 0
    furthest_marker_index = -1

    order_timeline_id = STATUS_TO_TIMELINE_ID.get(order.status)

    if order_timeline_id != "Processing":
        # --- SINGLE ORDER MARKER VIEW ---
        try:
            current_index = timeline_step_ids.index(order_timeline_id)
            furthest_marker_index = current_index
            progress = (current_index + 0.5) / total_steps * 100
            overall_progress_percent = (current_index / (total_steps - 1)) * 100 if total_steps > 1 else 0
            
            icon = 'fas fa-truck' if order.status in ["OutForDelivery", "OnRouteToCustomer"] else 'fas fa-box'
            
            markers.append({
                'type': 'order', 'position': progress, 'icon': icon,
                'count': 1, 'label': order.status
            })
        except ValueError:
            pass # Status not on timeline
    else:
        # --- BASKET MARKERS VIEW ---
        imaging_index = timeline_step_ids.index('Imaging')
        overall_progress_percent = (imaging_index / (total_steps - 1)) * 100 if total_steps > 1 else 0

        basket_groups = {}
        for basket in order.baskets:
            clean_status = basket.status.split('-')[0]
            basket_timeline_id = BASKET_STATUS_TO_TIMELINE_ID.get(clean_status)
            if basket_timeline_id:
                if basket_timeline_id not in basket_groups:
                    basket_groups[basket_timeline_id] = 0
                basket_groups[basket_timeline_id] += 1

        max_basket_index = -1
        for timeline_id, count in basket_groups.items():
            try:
                current_index = timeline_step_ids.index(timeline_id)
                max_basket_index = max(max_basket_index, current_index)
                progress = (current_index + 0.5) / total_steps * 100
                
                markers.append({
                    'type': 'basket', 'position': progress, 'icon': 'fas fa-box-open',
                    'count': count, 'label': f"{count} basket(s) at {timeline_id}"
                })
            except ValueError:
                continue
        furthest_marker_index = max_basket_index if max_basket_index > -1 else imaging_index

    # Determine step completion status for all steps
    for i, step in enumerate(TIMELINE_STEPS):
        status_class = "pending"
        if i < furthest_marker_index:
            status_class = "completed"
        elif i == furthest_marker_index:
            status_class = "active"
        step['status_class'] = status_class

    display_label = order.status.replace('_', ' ')
    # Find the label for the current active step for a nicer header
    if furthest_marker_index > -1:
        display_label = TIMELINE_STEPS[furthest_marker_index]['label']

    return templates.TemplateResponse("track.html", {
        "request": request,
        "order": order,
        "images": images,
        "key_events": key_events,
        "is_new": request.query_params.get("new") == "true",
        "display_label": display_label,
        "formatted_sla": formatted_sla,
        "timeline_steps": TIMELINE_STEPS,
        "markers": markers,
        "overall_progress_percent": overall_progress_percent,
    })