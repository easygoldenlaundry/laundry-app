# app/services/finance_calculator.py
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select, func
from typing import Dict, Any

from app.models import Order, Setting, FinanceEntry, Image, Withdrawal

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

def _calculate_water_cost_for_usage(kl_used: float, settings: Dict[str, Any]) -> float:
    """Calculates water cost based on a tiered pricing model."""
    cost = 0.0
    remaining_kl = kl_used
    # ... (rest of the function is unchanged)
    tier1_limit = settings.get('cost_water_kl_tier1_limit', 6)
    tier2_limit = settings.get('cost_water_kl_tier2_limit', 10.5)
    tier3_limit = settings.get('cost_water_kl_tier3_limit', 35)

    tier1_rate = settings.get('cost_water_kl_tier1_rate', 22.52)
    tier2_rate = settings.get('cost_water_kl_tier2_rate', 30.96)
    tier3_rate = settings.get('cost_water_kl_tier3_rate', 42.07)
    tier4_rate = settings.get('cost_water_kl_tier4_rate', 77.63)

    if remaining_kl > 0:
        usage_in_tier = min(remaining_kl, tier1_limit)
        cost += usage_in_tier * tier1_rate
        remaining_kl -= usage_in_tier
    if remaining_kl > 0:
        usage_in_tier = min(remaining_kl, tier2_limit - tier1_limit)
        cost += usage_in_tier * tier2_rate
        remaining_kl -= usage_in_tier
    if remaining_kl > 0:
        usage_in_tier = min(remaining_kl, tier3_limit - tier2_limit)
        cost += usage_in_tier * tier3_rate
        remaining_kl -= usage_in_tier
    if remaining_kl > 0:
        cost += remaining_kl * tier4_rate
        
    return cost

def create_finance_entries_for_order(order_id: int, session: Session):
    """
    Calculates and records the revenue and variable costs for a delivered order.
    This function is idempotent and will not create duplicate entries.
    """
    existing_entry = session.exec(select(FinanceEntry).where(FinanceEntry.order_id == order_id)).first()
    if existing_entry:
        return

    order = session.get(Order, order_id)
    if not order or order.status not in ["Delivered", "Closed"]:
        return

    settings = _get_settings_dict(session)
    standard_price = settings.get("standard_price_per_load", 210.0)
    
    if order.confirmed_load_count and order.confirmed_load_count > 0:
        revenue = order.confirmed_load_count * standard_price
        session.add(FinanceEntry(
            order_id=order.id,
            entry_type='revenue',
            amount=revenue,
            description=f"{order.confirmed_load_count} loads @ R{standard_price:.2f}/load"
        ))
    session.commit()

def get_start_date_for_period(period: str) -> datetime:
    """Returns the start datetime for a given period string."""
    now = datetime.now(timezone.utc)
    if period == 'today':
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'week':
        start_of_week = now - timedelta(days=now.weekday())
        return start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'month':
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == 'quarter':
        return now - timedelta(days=90)
    if period == 'year':
        return now - timedelta(days=365)
    return datetime.min.replace(tzinfo=timezone.utc) # 'all'

def get_dashboard_summary(session: Session, period: str) -> Dict[str, Any]:
    """Generates the high-level financial summary based on the Live Business Balance model."""
    settings = _get_settings_dict(session)
    start_date = get_start_date_for_period(period)
    
    # --- Live Business Balance Calculation ---
    total_revenue = session.exec(select(func.sum(FinanceEntry.amount)).where(FinanceEntry.entry_type == 'revenue', FinanceEntry.timestamp >= start_date)).one() or 0.0
    total_withdrawals = session.exec(select(func.sum(Withdrawal.amount)).where(Withdrawal.timestamp >= start_date)).one() or 0.0
    live_business_balance = total_revenue - total_withdrawals

    # --- Accrued Costs & Buffer Calculation (for guidance) ---
    now = datetime.now(timezone.utc)
    is_monthly_view = period == 'month'
    days_in_month = (now.replace(month=now.month % 12 + 1, day=1) - timedelta(days=1)).day
    days_so_far = now.day if is_monthly_view else days_in_month
    
    # --- Calculate fixed costs paid during THIS MONTH regardless of selected period ---
    start_of_current_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    fixed_cost_withdrawals = session.exec(
        select(Withdrawal.description, func.sum(Withdrawal.amount))
        .where(Withdrawal.withdrawal_type == 'fixed_cost', Withdrawal.timestamp >= start_of_current_month)
        .group_by(Withdrawal.description)
    ).all()
    paid_fixed_costs = {desc: amount for desc, amount in fixed_cost_withdrawals}

    # Map description from UI to setting key
    fixed_cost_map = {
        "Rent Payment": "cost_rent_monthly",
        "Insurance Payment": "cost_insurance_monthly",
        "Base Electricity Payment": "cost_base_electricity_monthly"
    }

    fraction_of_month = days_so_far / days_in_month
    accrued_bills = 0
    for desc, key in fixed_cost_map.items():
        monthly_cost = settings.get(key, 0.0)
        accrued_amount = monthly_cost * fraction_of_month
        paid_amount = paid_fixed_costs.get(desc, 0.0)
        accrued_bills += max(0, accrued_amount - paid_amount)

    # Water and electricity costs are based on real-time trackers for the current month
    total_elec_kwh_used = settings.get('monthly_tracker_electricity_kwh', 0.0)
    elec_kwh_rate = settings.get('cost_electricity_kwh', 3.91)
    
    accrued_elec_cost = total_elec_kwh_used * elec_kwh_rate
    
    set_aside_for_bills = accrued_bills + accrued_elec_cost
    
    safety_buffer_percent = settings.get('finance_safety_buffer_percent', 10.0)
    # Use total revenue for the period for the buffer calculation
    safety_buffer_target = total_revenue * (safety_buffer_percent / 100)

    # --- Operator Mood Guidance ---
    total_coverage_needed = set_aside_for_bills + safety_buffer_target
    guidance_message = "Healthy: Your business balance is sufficient to cover upcoming costs and savings."
    if live_business_balance < total_coverage_needed:
        guidance_message = "Caution: Your balance is low. Avoid taking profits to ensure you can cover bills and savings."
    if live_business_balance < set_aside_for_bills:
        guidance_message = "Warning: Your balance may not be enough to cover this month's bills. Prioritize essential payments."

    # --- THIS IS THE FIX: Calculate detailed electricity tracker data ---
    kwh_per_load = settings.get('usage_kwh_per_wash', 1.5) + settings.get('usage_kwh_per_dry', 4.0)
    electricity_budget = settings.get('monthly_budget_electricity_kwh', 0.0)
    electricity_tracker_data = {
        "budget": electricity_budget,
        "used": total_elec_kwh_used,
        "remaining": electricity_budget - total_elec_kwh_used,
        "threshold": 15 * kwh_per_load, # 15 loads worth of electricity
    }

    return {
        "period": period,
        "live_business_balance": live_business_balance,
        "set_aside_for_bills": set_aside_for_bills,
        "safety_buffer_target": safety_buffer_target,
        "total_revenue": total_revenue,
        "total_withdrawals": total_withdrawals,
        "guidance_message": guidance_message,
        "electricity_tracker": electricity_tracker_data,
    }