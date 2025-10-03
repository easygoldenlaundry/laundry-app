# app/queries/dashboard_queries.py
"""
This module contains functions for calculating all Key Performance Indicators (KPIs)
and data points required by the Admin Command Room dashboard.
"""
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select, func
from sqlalchemy.orm import selectinload
from statistics import median
from typing import Dict, Any, List, Optional
import math
import json # For parsing Event.meta

from app.models import Order, Event, Claim, Image, Machine, Station, User, Driver, Basket, Setting, Customer

def _get_settings_dict(session: Session) -> Dict[str, Any]:
    """Helper to fetch all settings and cast them to appropriate types."""
    settings = session.exec(select(Setting)).all()
    settings_dict = {}
    for s in settings:
        try:
            settings_dict[s.key] = float(s.value)
        except (ValueError, TypeError):
            settings_dict[s.key] = s.value
    return settings_dict


def _get_percentile(data: List[float], percentile: float) -> float:
    """
    [FIXED] Helper to get a percentile from a sorted list of data using linear interpolation.
    This is more accurate for small datasets.
    """
    if not data:
        return 0.0
    
    data.sort()
    n = len(data)
    if n == 0:
        return 0.0

    if percentile <= 0: return data[0]
    if percentile >= 1: return data[-1]

    k = (n - 1) * percentile
    f = math.floor(k)
    c = math.ceil(k)

    if f == c:
        return data[int(k)]
    
    d0 = data[int(f)]
    d1 = data[int(c)]
    return d0 + (d1 - d0) * (k - f)

def get_turnaround_kpi(session: Session, window_hours: int = 24) -> Dict[str, Any]:
    """
    Calculates the percentage of orders with a turnaround time <= 2.5 hours (150 minutes)
    and provides 50th, 90th, and 95th percentile turnaround times.
    Turnaround is defined as `delivered_at` - `picked_up_at`.
    """
    settings = _get_settings_dict(session)
    goal_minutes = settings.get("kpi_goal_turnaround_minutes", 150)
    start_time = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    
    orders = session.exec(
        select(Order).where(
            Order.delivered_at >= start_time,
            Order.picked_up_at != None,
            Order.delivered_at != None
        )
    ).all()

    if not orders:
        return {"percentage_on_time": 100, "total_completed": 0, "p50_minutes": 0, "p90_minutes": 0, "p95_minutes": 0, "goal_minutes": goal_minutes}

    turnaround_times_minutes = []
    for order in orders:
        turnaround = (order.delivered_at - order.picked_up_at).total_seconds() / 60
        turnaround_times_minutes.append(turnaround)
    
    total_completed = len(turnaround_times_minutes)
    on_time_count = sum(1 for t in turnaround_times_minutes if t <= goal_minutes)
    
    if total_completed == 0:
        return {"percentage_on_time": 100, "total_completed": 0, "p50_minutes": 0, "p90_minutes": 0, "p95_minutes": 0, "goal_minutes": goal_minutes}

    p50 = _get_percentile(turnaround_times_minutes, 0.50)
    p90 = _get_percentile(turnaround_times_minutes, 0.90)
    p95 = _get_percentile(turnaround_times_minutes, 0.95)
    
    return {
        "percentage_on_time": (on_time_count / total_completed) * 100,
        "total_completed": total_completed,
        "p50_minutes": round(p50, 1),
        "p90_minutes": round(p90, 1),
        "p95_minutes": round(p95, 1),
        "goal_minutes": goal_minutes
    }

def get_pickup_kpi(session: Session, window_hours: int = 24) -> Dict[str, Any]:
    """
    Calculates the percentage of pickups completed within 15 minutes of order creation.
    Pickup time is `picked_up_at` - `created_at`.
    """
    settings = _get_settings_dict(session)
    goal_minutes = settings.get("kpi_goal_pickup_minutes", 15)
    start_time = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    
    orders = session.exec(
        select(Order).where(
            Order.created_at >= start_time,
            Order.picked_up_at != None
        )
    ).all()

    if not orders:
        return {"percentage_on_time": 100, "total_pickups": 0, "median_pickup_time": 0, "goal_minutes": goal_minutes}

    pickup_times = [(o.picked_up_at - o.created_at).total_seconds() / 60 for o in orders]
    total_pickups = len(pickup_times)
    on_time_count = sum(1 for t in pickup_times if t <= goal_minutes)
    
    if total_pickups == 0:
        return {"percentage_on_time": 100, "total_pickups": 0, "median_pickup_time": 0, "goal_minutes": goal_minutes}

    return {
        "percentage_on_time": (on_time_count / total_pickups) * 100,
        "total_pickups": total_pickups,
        "median_pickup_time": round(median(pickup_times), 1),
        "goal_minutes": goal_minutes
    }

def get_delivery_kpi(session: Session, window_hours: int = 24) -> Dict[str, Any]:
    """
    Calculates the percentage of deliveries completed within 15 minutes of being ready for delivery.
    Delivery time is `delivered_at` - `out_for_delivery_at`.
    """
    settings = _get_settings_dict(session)
    goal_minutes = settings.get("kpi_goal_delivery_minutes", 15)
    start_time = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    
    orders = session.exec(
        select(Order).where(
            Order.out_for_delivery_at >= start_time,
            Order.delivered_at != None
        )
    ).all()

    if not orders:
        return {"percentage_on_time": 100, "total_deliveries": 0, "avg_delivery_time": 0, "goal_minutes": goal_minutes}

    delivery_times = [(o.delivered_at - o.out_for_delivery_at).total_seconds() / 60 for o in orders]
    total_deliveries = len(delivery_times)
    on_time_count = sum(1 for t in delivery_times if t <= goal_minutes)
    
    if total_deliveries == 0:
        return {"percentage_on_time": 100, "total_deliveries": 0, "avg_delivery_time": 0, "goal_minutes": goal_minutes}

    return {
        "percentage_on_time": (on_time_count / total_deliveries) * 100,
        "total_deliveries": total_deliveries,
        "avg_delivery_time": round(sum(delivery_times) / total_deliveries, 1),
        "goal_minutes": goal_minutes
    }

def get_claim_rate_kpi(session: Session, window_hours: int = 24) -> Dict[str, Any]:
    """Calculates the percentage of orders that have a claim filed against them."""
    start_time = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    
    total_orders_in_window = session.exec(
        select(func.count(Order.id))
        .where(Order.created_at >= start_time)
    ).one()

    if total_orders_in_window == 0:
        return {"claim_rate_percent": 0.0, "orders_with_claims": 0, "total_orders": 0}

    orders_with_claims = session.exec(
        select(func.count(func.distinct(Claim.order_id)))
        .where(Claim.created_at >= start_time)
    ).one()

    return {
        "claim_rate_percent": (orders_with_claims / total_orders_in_window) * 100 if total_orders_in_window > 0 else 0,
        "orders_with_claims": orders_with_claims,
        "total_orders": total_orders_in_window
    }


def get_active_inflight_orders(session: Session) -> List[Order]:
    """Returns a list of all active orders, enriched with SLA urgency data."""
    TERMINAL_STATUSES = ["Delivered", "Closed", "Cancelled"]
    
    orders = session.exec(
        select(Order)
        .where(Order.status.notin_(TERMINAL_STATUSES))
        .options(selectinload(Order.baskets))
        .order_by(Order.sla_deadline.asc().nulls_last(), Order.created_at.asc())
    ).all()
    
    return orders

def get_claims_summary(session: Session, window_hours: int = 24) -> Dict[str, Any]:
    """Returns a summary of claims activity."""
    start_time = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    
    claims_in_window = session.exec(select(Claim).where(Claim.created_at >= start_time)).all()
    
    open_count = sum(1 for c in claims_in_window if c.status == 'open')
    total_compensation = sum(c.amount for c in claims_in_window if c.amount is not None)
    
    return {
        "count_today": len(claims_in_window),
        "open_count": open_count,
        "total_compensation": round(total_compensation, 2)
    }

def get_station_metrics(session: Session, station_type: str, window_hours: int = 24) -> Dict[str, Any]:
    """Computes detailed metrics for a specific station."""
    station = session.exec(select(Station).where(Station.type == station_type)).one_or_none()
    
    metrics = { "queue_length": 0, "utilization_pct": 0.0, "bottleneck": False, "avg_time": 0.0, "median_time": 0.0, "p95_time": 0.0, "throughput_h": 0.0 }
    if not station: return metrics

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=window_hours)
    
    if station_type == "qa":
        metrics["queue_length"] = session.exec(select(func.count(Order.id)).where(Order.status == "QA")).one()
    else:
        metrics["queue_length"] = session.exec(select(func.count(Basket.id)).where(Basket.status == station_type.capitalize())).one()

    if station_type in ["washing", "drying", "folding"]:
        machines = session.exec(select(Machine).where(Machine.station_id == station.id)).all()
        total_machines = len(machines)
        running_machines = sum(1 for m in machines if m.state == 'running')
        metrics["utilization_pct"] = (running_machines / total_machines) * 100 if total_machines > 0 else 0
    
    processing_durations = []
    relevant_events = session.exec(select(Event).where(Event.timestamp >= start_time).order_by(Event.timestamp.asc())).all()

    if station_type == "imaging":
        completed_orders = session.exec(select(Order).where(Order.imaging_completed_at >= start_time, Order.imaging_started_at != None)).all()
        for order in completed_orders:
            processing_durations.append((order.imaging_completed_at - order.imaging_started_at).total_seconds() / 60)
    
    elif station_type == "qa":
        completed_orders = session.exec(select(Order).where(Order.qa_started_at >= start_time).options(selectinload(Order.events))).all()
        for order in completed_orders:
            qa_start_ts = order.qa_started_at
            qa_end_event = next((e for e in order.events if e.from_status == "QA" and e.timestamp >= qa_start_ts), None)
            if qa_end_event:
                processing_durations.append((qa_end_event.timestamp - qa_start_ts).total_seconds() / 60)

    elif station_type in ["pretreat", "washing", "drying", "folding"]:
        starts = {}
        for event in relevant_events:
            if event.to_status and f"Started-{station_type}" in event.to_status:
                try:
                    basket_id = json.loads(event.meta or '{}').get('basket_id')
                    if basket_id:
                        starts[basket_id] = event.timestamp
                except (json.JSONDecodeError, AttributeError):
                    continue
        
        for event in relevant_events:
            if event.to_status and f"Finished-{station_type}" in event.to_status:
                try:
                    basket_id = json.loads(event.meta or '{}').get('basket_id')
                    if basket_id and basket_id in starts and event.timestamp > starts[basket_id]:
                        duration = (event.timestamp - starts[basket_id]).total_seconds() / 60
                        processing_durations.append(duration)
                        del starts[basket_id]
                except (json.JSONDecodeError, AttributeError):
                    continue

    if processing_durations:
        metrics["avg_time"] = round(sum(processing_durations) / len(processing_durations), 1)
        metrics["median_time"] = round(median(processing_durations), 1)
        metrics["p95_time"] = round(_get_percentile(processing_durations, 0.95), 1)
    
    metrics["throughput_h"] = round(len(processing_durations) / window_hours, 1) if window_hours > 0 else len(processing_durations)
    effective_capacity = station.capacity or 5
    metrics["bottleneck"] = metrics["queue_length"] > (effective_capacity * 2) or metrics["utilization_pct"] > 85
    
    return metrics


def get_all_orders(session: Session) -> select:
    """Returns a select statement for all orders with basic relations for UI display."""
    return (
        select(Order)
        .options(
            selectinload(Order.customer), 
            selectinload(Order.baskets), 
            selectinload(Order.claims), 
            selectinload(Order.events),
            selectinload(Order.images)
        )
        .order_by(Order.created_at.desc())
    )

def get_aggregated_stats(session: Session, timeframe_days: int) -> Dict[str, Any]:
    """Calculates various aggregated statistics over a given timeframe (in days)."""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=timeframe_days)

    completed_orders = session.exec(select(Order).where(Order.delivered_at >= start_time).options(selectinload(Order.events))).all()
    created_orders = session.exec(select(Order).where(Order.created_at >= start_time)).all()

    price_setting = session.get(Setting, "price_per_load")
    price_per_load = float(price_setting.value) if price_setting else 0.0
    total_revenue = sum(
        (o.confirmed_load_count * price_per_load)
        for o in completed_orders
        if o.confirmed_load_count is not None
    )
    
    total_orders_completed, total_orders_created = len(completed_orders), len(created_orders)
    
    turnaround_times_minutes, pickup_times_minutes = [], []
    for order in completed_orders:
        if order.picked_up_at and order.delivered_at:
            turnaround_times_minutes.append((order.delivered_at - order.picked_up_at).total_seconds() / 60)
        if order.created_at and order.picked_up_at:
            pickup_times_minutes.append((order.picked_up_at - order.created_at).total_seconds() / 60)

    imaging_durations, qa_durations, total_stains_flagged, qa_passed_count, qa_failed_count = [], [], 0, 0, 0
    for order in completed_orders:
        if order.imaging_started_at and order.processing_started_at:
            imaging_durations.append((order.processing_started_at - order.imaging_started_at).total_seconds() / 60)
        qa_start = next((e for e in order.events if e.to_status == "QA"), None)
        if qa_start:
            qa_end = next((e for e in order.events if (e.to_status == "ReadyForDelivery" or ("Processing" in e.to_status and "qa_failed_by" in str(e.meta))) and e.timestamp > qa_start.timestamp), None)
            if qa_end:
                qa_durations.append((qa_end.timestamp - qa_start.timestamp).total_seconds() / 60)
                if qa_end.to_status == "ReadyForDelivery": qa_passed_count += 1
                else: qa_failed_count += 1
        if session.exec(select(Image).where(Image.order_id == order.id, Image.is_stain == True)).first():
            total_stains_flagged += 1
    
    all_events = session.exec(select(Event).where(Event.timestamp >= start_time)).all()
    pretreat_d, washing_d, drying_d, folding_d = [], [], [], []

    starts = {}
    for event in all_events:
        if event.to_status and "Started" in event.to_status:
            try:
                basket_id = json.loads(event.meta or '{}').get('basket_id')
                station_type = event.to_status.split('-')[-1]
                if basket_id:
                    starts[f"{basket_id}_{station_type}"] = event.timestamp
            except (json.JSONDecodeError, AttributeError):
                continue

    for event in all_events:
         if event.to_status and "Finished" in event.to_status:
            try:
                basket_id = json.loads(event.meta or '{}').get('basket_id')
                station_type = event.to_status.split('-')[-1]
                start_key = f"{basket_id}_{station_type}"
                if basket_id and start_key in starts:
                    duration = (event.timestamp - starts[start_key]).total_seconds() / 60
                    if station_type == 'pretreat': pretreat_d.append(duration)
                    elif station_type == 'washing': washing_d.append(duration)
                    elif station_type == 'drying': drying_d.append(duration)
                    elif station_type == 'folding': folding_d.append(duration)
                    del starts[start_key]
            except (json.JSONDecodeError, AttributeError):
                continue
    
    def safe_avg(data): return round(sum(data) / len(data), 2) if data else 0.0
    total_items = sum(o.total_items for o in completed_orders)
    
    return {
        "timeframe": f"{timeframe_days} days",
        "total_orders_created": total_orders_created,
        "total_orders_completed": total_orders_completed,
        "total_revenue": total_revenue,
        "avg_turnaround_minutes": safe_avg(turnaround_times_minutes),
        "avg_pickup_minutes": safe_avg(pickup_times_minutes),
        "avg_items_per_order": round(total_items / total_orders_completed, 1) if total_orders_completed else 0,
        "total_claims": session.exec(select(func.count(Claim.id)).where(Claim.created_at >= start_time)).one(),
        "total_compensation": round(session.exec(select(func.sum(Claim.amount)).where(Claim.created_at >= start_time, Claim.amount != None)).one() or 0, 2),
        "avg_imaging_time": safe_avg(imaging_durations),
        "avg_pretreat_time": safe_avg(pretreat_d),
        "avg_washing_time": safe_avg(washing_d),
        "avg_drying_time": safe_avg(drying_d),
        "avg_folding_time": safe_avg(folding_d),
        "avg_qa_time": safe_avg(qa_durations),
        "percent_with_stains": (total_stains_flagged / total_orders_created) * 100 if total_orders_created > 0 else 0,
        "percent_qa_passed": (qa_passed_count / (qa_passed_count + qa_failed_count)) * 100 if (qa_passed_count + qa_failed_count) > 0 else 0,
        "percent_qa_failed": (qa_failed_count / (qa_passed_count + qa_failed_count)) * 100 if (qa_passed_count + qa_failed_count) > 0 else 0,
    }


def get_retention_kpis(session: Session) -> Dict[str, Any]:
    """
    Calculates key customer retention metrics:
    1. Retention Rate (%): Customers active in the last 90 days.
    2. Average Lifespan: Avg. time between a customer's first and last order.
    3. Order Frequency: Avg. number of orders per customer.
    4. LTV: Average revenue generated per customer.
    """
    all_customers = session.exec(
        select(Customer).options(selectinload(Customer.orders))
    ).all()

    total_customers = len(all_customers)
    if total_customers == 0:
        return {
            "retention_percentage": 0, "avg_lifespan_days": 0,
            "avg_lifespan_months": 0, "avg_lifespan_rem_days": 0,
            "avg_orders_per_customer": 0, "ltv": 0
        }

    price_setting = session.get(Setting, "price_per_load")
    price_per_load = float(price_setting.value) if price_setting else 0.0

    retention_threshold = datetime.now(timezone.utc) - timedelta(days=90)
    retained_customer_count = 0
    total_lifespan_days = 0
    total_order_count = 0
    total_revenue_all_time = 0

    for customer in all_customers:
        if not customer.orders:
            continue
        
        order_dates = []
        for o in customer.orders:
            created_at_aware = o.created_at
            if created_at_aware.tzinfo is None:
                created_at_aware = created_at_aware.replace(tzinfo=timezone.utc)
            order_dates.append(created_at_aware)
        
        if not order_dates:
            continue
        
        first_order_date = min(order_dates)
        last_order_date = max(order_dates)

        if last_order_date > retention_threshold:
            retained_customer_count += 1
        
        lifespan = (last_order_date - first_order_date).days
        total_lifespan_days += lifespan
        total_order_count += len(customer.orders)
        
        customer_revenue = sum(
            (o.confirmed_load_count * price_per_load)
            for o in customer.orders
            if o.confirmed_load_count is not None
        )
        total_revenue_all_time += customer_revenue

    avg_lifespan_days = total_lifespan_days / total_customers
    avg_lifespan_months = math.floor(avg_lifespan_days / 30.44)
    avg_lifespan_rem_days = math.floor(avg_lifespan_days % 30.44)

    return {
        "retention_percentage": (retained_customer_count / total_customers) * 100,
        "avg_lifespan_days": round(avg_lifespan_days),
        "avg_lifespan_months": avg_lifespan_months,
        "avg_lifespan_rem_days": avg_lifespan_rem_days,
        "avg_orders_per_customer": total_order_count / total_customers,
        "ltv": total_revenue_all_time / total_customers if total_customers > 0 else 0
    }


def get_claims_resolution_kpi(session: Session, window_hours: int = 72) -> Dict[str, Any]:
    """
    Calculates KPIs for claim handling efficiency.
    - % of claims handled by a human within 5 minutes.
    - % of total claims that are auto-resolved.
    """
    settings = _get_settings_dict(session)
    goal_seconds = settings.get("kpi_goal_claim_minutes", 5) * 60
    start_time = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    
    resolved_claims = session.exec(
        select(Claim).where(
            Claim.resolved_at >= start_time,
            Claim.status.in_(["resolved", "denied"])
        )
    ).all()

    if not resolved_claims:
        return {"on_time_percentage": 100, "auto_claim_percentage": 0, "goal_minutes": goal_seconds / 60}

    human_resolved_on_time = 0
    human_resolved_total = 0
    auto_resolved_total = 0

    for claim in resolved_claims:
        if claim.notes and "[Auto-resolved" in claim.notes:
            auto_resolved_total += 1
        else:
            human_resolved_total += 1

            resolved_at_aware = claim.resolved_at
            
            if resolved_at_aware and resolved_at_aware.tzinfo is None:
                resolved_at_aware = resolved_at_aware.replace(tzinfo=timezone.utc)
            
            created_at_aware = claim.created_at
            if created_at_aware and created_at_aware.tzinfo is None:
                created_at_aware = created_at_aware.replace(tzinfo=timezone.utc)
            
            if resolved_at_aware and created_at_aware:
                resolve_time_seconds = (resolved_at_aware - created_at_aware).total_seconds()
                if resolve_time_seconds <= goal_seconds:
                    human_resolved_on_time += 1
    
    total_resolved = human_resolved_total + auto_resolved_total

    return {
        "on_time_percentage": (human_resolved_on_time / human_resolved_total) * 100 if human_resolved_total > 0 else 100,
        "auto_claim_percentage": (auto_resolved_total / total_resolved) * 100 if total_resolved > 0 else 0,
        "goal_minutes": goal_seconds / 60
    }