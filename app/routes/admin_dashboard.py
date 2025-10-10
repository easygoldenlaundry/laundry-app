# app/routes/admin_dashboard.py
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlmodel import Session
from app.db import get_session
from app.auth import get_current_admin_user
from app.queries import dashboard_queries
from fastapi.templating import Jinja2Templates
from typing import List, Dict, Any, Optional
import json

router = APIRouter(
    prefix="/admin",
    tags=["Admin Dashboard"],
    dependencies=[Depends(get_current_admin_user)]
)

templates = Jinja2Templates(directory="app/templates")

@router.get("/command-room", response_class=HTMLResponse)
async def get_command_room(request: Request):
    """Serves the main Admin Command Room page."""
    return templates.TemplateResponse("admin/command_room.html", {"request": request})

# --- API Endpoints for Dashboard Widgets ---

@router.get("/api/dashboard/kpis")
async def get_dashboard_kpis(session: Session = Depends(get_session)):
    """Fetches all executive-level KPIs for the cards in Row 1."""
    active_orders = dashboard_queries.get_active_inflight_orders(session)
    
    return {
        "retention": dashboard_queries.get_retention_kpis(session),
        "turnaround": dashboard_queries.get_turnaround_kpi(session),
        "pickup": dashboard_queries.get_pickup_kpi(session),
        "delivery": dashboard_queries.get_delivery_kpi(session),
        "claim_rate": dashboard_queries.get_claim_rate_kpi(session),
        "claims_resolution": dashboard_queries.get_claims_resolution_kpi(session),
        "claims": dashboard_queries.get_claims_summary(session),
        "active_orders_count": len(active_orders)
    }

@router.get("/api/dashboard/orders")
async def get_dashboard_orders_table(session: Session = Depends(get_session)):
    """Fetches the detailed data for the real-time orders table."""
    return dashboard_queries.get_active_inflight_orders(session)

@router.get("/api/dashboard/station-metrics")
async def get_all_station_metrics(session: Session = Depends(get_session)):
    """Fetches metrics for all key stations."""
    stations = ["imaging", "pretreat", "washing", "drying", "folding", "qa"]
    metrics = {s_type: dashboard_queries.get_station_metrics(session, s_type) for s_type in stations}
    return metrics

# --- [NEW] Endpoints for Raw & Aggregated Tables ---

@router.get("/api/dashboard/all-orders")
async def get_all_orders_data(
    request: Request,
    session: Session = Depends(get_session)
):
    """Fetches all orders for the detailed historical table."""
    orders = session.exec(dashboard_queries.get_all_orders(session)).all()
    
    # Exclude relationships that cause N+1 queries, but keep the ones we need
    exclude_relations = {
        'claims', 'messages', 'finance_entries', 'bags'
    }

    serialized_orders = []
    for order in orders:
        order_dict = json.loads(order.json(exclude=exclude_relations))
        order_dict['customer_name'] = order.customer.full_name if order.customer else 'N/A'
        # Use eager-loaded relationships to avoid N+1 queries
        order_dict['events'] = [json.loads(e.json()) for e in order.events]
        order_dict['baskets'] = [json.loads(b.json()) for b in order.baskets]
        order_dict['images'] = [json.loads(i.json()) for i in order.images]
        serialized_orders.append(order_dict)
    return serialized_orders

@router.get("/api/dashboard/aggregated-stats")
async def get_aggregated_statistics_data(
    request: Request,
    timeframe: Optional[str] = "7days", # e.g., "7days", "30days", "1year"
    session: Session = Depends(get_session)
):
    """Fetches aggregated statistics based on a given timeframe."""
    timeframe_map = {
        "7days": 7,
        "30days": 30,
        "1year": 365,
        "alltime": 9999 # Effectively all time
    }
    days = timeframe_map.get(timeframe, 7) # Default to 7 days
    stats = dashboard_queries.get_aggregated_stats(session, days)
    return stats