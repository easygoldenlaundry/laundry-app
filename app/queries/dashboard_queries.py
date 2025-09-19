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

from app.models import Order, Event, Claim, Image, Machine, Station, User, Driver, Basket


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
    start_time = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    
    orders = session.exec(
        select(Order).where(
            Order.delivered_at >= start_time,
            Order.picked_up_at != None,
            Order.delivered_at != None
        )
    ).all()

    if not orders:
        return {"percentage_on_time": 100, "total_completed": 0, "p50_minutes": 0, "p90_minutes": 0, "p95_minutes": 0}

    turnaround_times_minutes = []
    for order in orders:
        turnaround = (order.delivered_at - order.picked_up_at).total_seconds() / 60
        turnaround_times_minutes.append(turnaround)
    
    total_completed = len(turnaround_times_minutes)
    on_time_count = sum(1 for t in turnaround_times_minutes if t <= 150)
    
    if total_completed == 0:
        return {"percentage_on_time": 100, "total_completed": 0, "p50_minutes": 0, "p90_minutes": 0, "p95_minutes": 0}

    p50 = _get_percentile(turnaround_times_minutes, 0.50)
    p90 = _get_percentile(turnaround_times_minutes, 0.90)
    p95 = _get_percentile(turnaround_times_minutes, 0.95)
    
    return {
        "percentage_on_time": (on_time_count / total_completed) * 100,
        "total_completed": total_completed,
        "p50_minutes": round(p50, 1),
        "p90_minutes": round(p90, 1),
        "p95_minutes": round(p95, 1)
    }

def get_pickup_kpi(session: Session, window_hours: int = 24) -> Dict[str, Any]:
    """
    Calculates the percentage of pickups completed within 15 minutes of order creation.
    Pickup time is `picked_up_at` - `created_at`.
    """
    start_time = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    
    orders = session.exec(
        select(Order).where(
            Order.created_at >= start_time,
            Order.picked_up_at != None
        )
    ).all()

    if not orders:
        return {"percentage_on_time": 100, "total_pickups": 0, "median_pickup_time": 0}

    pickup_times = [(o.picked_up_at - o.created_at).total_seconds() / 60 for o in orders]
    total_pickups = len(pickup_times)
    on_time_count = sum(1 for t in pickup_times if t <= 15)
    
    if total_pickups == 0:
        return {"percentage_on_time": 100, "total_pickups": 0, "median_pickup_time": 0}

    return {
        "percentage_on_time": (on_time_count / total_pickups) * 100,
        "total_pickups": total_pickups,
        "median_pickup_time": round(median(pickup_times), 1)
    }

def get_delivery_kpi(session: Session, window_hours: int = 24) -> Dict[str, Any]:
    """
    Calculates the percentage of deliveries completed within 15 minutes of being ready for delivery.
    Delivery time is `delivered_at` - `out_for_delivery_at`.
    """
    start_time = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    
    orders = session.exec(
        select(Order).where(
            Order.out_for_delivery_at >= start_time,
            Order.delivered_at != None
        )
    ).all()

    if not orders:
        return {"percentage_on_time": 100, "total_deliveries": 0, "avg_delivery_time": 0}

    delivery_times = [(o.delivered_at - o.out_for_delivery_at).total_seconds() / 60 for o in orders]
    total_deliveries = len(delivery_times)
    on_time_count = sum(1 for t in delivery_times if t <= 15)
    
    if total_deliveries == 0:
        return {"percentage_on_time": 100, "total_deliveries": 0, "avg_delivery_time": 0}

    return {
        "percentage_on_time": (on_time_count / total_deliveries) * 100,
        "total_deliveries": total_deliveries,
        "avg_delivery_time": round(sum(delivery_times) / total_deliveries, 1)
    }

def get_image_coverage_kpi(session: Session, window_hours: int = 24) -> Dict[str, Any]:
    """Calculates the percentage of items that were successfully imaged."""
    start_time = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    
    result = session.exec(
        select(func.sum(Order.total_items), func.sum(Order.imaged_items_count))
        .where(Order.imaging_completed_at >= start_time, Order.imaging_completed_at <= datetime.now(timezone.utc))
    ).one_or_none()

    total_items, imaged_items = result or (0, 0)
    total_items = total_items or 0
    imaged_items = imaged_items or 0

    return {
        "total_items": total_items,
        "imaged_items": imaged_items,
        "coverage_percent": (imaged_items / total_items) * 100 if total_items > 0 else 100
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
    
    metrics = { "queue_length": 0, "utilization_pct": 0.0, "bottleneck": False, "avg_time": 0.0, "median_time": 0.0, "p95_time": 0.0, "throughput_h": 0 }
    if not station: return metrics

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=window_hours)
    
    # Queue Length
    if station_type == "qa":
        metrics["queue_length"] = session.exec(select(func.count(Order.id)).where(Order.status == "QA")).one()
    else:
        metrics["queue_length"] = session.exec(select(func.count(Basket.id)).where(Basket.status == station_type.capitalize())).one()

    # Machine Utilization
    if station_type in ["washing", "drying", "folding"]:
        machines = session.exec(select(Machine).where(Machine.station_id == station.id)).all()
        total_machines = len(machines)
        running_machines = sum(1 for m in machines if m.state == 'running')
        metrics["utilization_pct"] = (running_machines / total_machines) * 100 if total_machines > 0 else 0
    
    # Processing Times and Throughput
    processing_durations, throughput_count = [], 0
    relevant_events = session.exec(select(Event).where(Event.timestamp >= start_time).order_by(Event.timestamp)).all()

    if station_type == "imaging":
        for order in session.exec(select(Order).where(Order.imaging_completed_at >= start_time)).all():
            if order.imaging_started_at:
                processing_durations.append((order.imaging_completed_at - order.imaging_started_at).total_seconds() / 60)
                throughput_count += 1
    elif station_type == "qa":
        for order in session.exec(select(Order).where(Order.qa_started_at >= start_time).options(selectinload(Order.events))).all():
            qa_start_event = next((e for e in order.events if e.to_status == "QA"), None)
            qa_end_event = next((e for e in order.events if (e.to_status == "ReadyForDelivery" or ("Processing" in e.to_status and "qa_failed_by" in str(e.meta))) and e.timestamp > (qa_start_event.timestamp if qa_start_event else datetime.min.replace(tzinfo=timezone.utc))), None)
            if qa_start_event and qa_end_event:
                processing_durations.append((qa_end_event.timestamp - qa_start_event.timestamp).total_seconds() / 60)
                throughput_count += 1
    elif station_type in ["pretreat", "washing", "drying", "folding"]:
        finished_baskets = {}
        for event in relevant_events:
            if event.to_status and f"Finished-{station_type}" in event.to_status:
                try:
                    basket_id = json.loads(event.meta or '{}').get('basket_id')
                    if basket_id: finished_baskets[f"{event.order_id}_{basket_id}"] = event
                except: pass
        
        for key, finish_event in finished_baskets.items():
            basket_id = key.split('_')[-1]
            start_event_str = f"Basket-{basket_id}-Started-{station_type}"
            start_event = next((e for e in relevant_events if e.to_status == start_event_str and e.timestamp < finish_event.timestamp), None)
            if start_event:
                processing_durations.append((finish_event.timestamp - start_event.timestamp).total_seconds() / 60)
                throughput_count += 1

    if processing_durations:
        metrics["avg_time"] = round(sum(processing_durations) / len(processing_durations), 1)
        metrics["median_time"] = round(median(processing_durations), 1)
        metrics["p95_time"] = round(_get_percentile(processing_durations, 0.95), 1)
    metrics["throughput_h"] = round(throughput_count / window_hours, 1) if window_hours > 0 else throughput_count

    effective_capacity = station.capacity or 5
    metrics["bottleneck"] = metrics["queue_length"] > (effective_capacity * 2) or metrics["utilization_pct"] > 85
    
    return metrics

def get_all_orders(session: Session) -> select:
    """Returns a select statement for all orders with basic relations and events for UI display."""
    return (
        select(Order)
        .options(selectinload(Order.customer), selectinload(Order.baskets), selectinload(Order.claims), selectinload(Order.events))
        .order_by(Order.created_at.desc())
    )

def get_aggregated_stats(session: Session, timeframe_days: int) -> Dict[str, Any]:
    """Calculates various aggregated statistics over a given timeframe (in days)."""
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=timeframe_days)

    completed_orders = session.exec(select(Order).where(Order.delivered_at >= start_time).options(selectinload(Order.events))).all()
    created_orders = session.exec(select(Order).where(Order.created_at >= start_time)).all()

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

    finished_baskets = {}
    for event in all_events:
        if event.to_status and "Finished" in event.to_status:
            try:
                basket_id = json.loads(event.meta or '{}').get('basket_id')
                if basket_id: finished_baskets[f"{event.order_id}_{basket_id}_{event.to_status}"] = event
            except: pass
    
    for key, finish_event in finished_baskets.items():
        _, basket_id, finish_status = key.split('_', 2)
        station_type = finish_status.split('-')[-1]
        start_event_str = f"Basket-{basket_id}-Started-{station_type}"
        start_event = next((e for e in all_events if e.to_status == start_event_str and e.timestamp < finish_event.timestamp and json.loads(e.meta or '{}').get('basket_id') == int(basket_id)), None)
        if start_event:
            duration = (finish_event.timestamp - start_event.timestamp).total_seconds() / 60
            if station_type == 'Pretreat': pretreat_d.append(duration)
            elif station_type == 'washing': washing_d.append(duration)
            elif station_type == 'drying': drying_d.append(duration)
            elif station_type == 'folding': folding_d.append(duration)

    def safe_avg(data): return round(sum(data) / len(data), 1) if data else 0
    total_items = sum(o.total_items for o in completed_orders)
    
    return {
        "timeframe": f"{timeframe_days} days",
        "total_orders_created": total_orders_created,
        "total_orders_completed": total_orders_completed,
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