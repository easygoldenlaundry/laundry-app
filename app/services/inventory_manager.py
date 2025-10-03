# app/services/inventory_manager.py
import logging
from sqlmodel import Session, select, func

from app.models import Order, Setting, Image, InventoryItem, Withdrawal
from app.sockets import broadcast_admin_notification
import asyncio

def _get_settings_dict(session: Session) -> dict:
    """Helper to fetch all settings."""
    settings_db = session.exec(select(Setting)).all()
    settings = {}
    for s in settings_db:
        try:
            settings[s.key] = float(s.value)
        except (ValueError, TypeError):
            settings[s.key] = s.value
    return settings

async def check_for_low_stock(session: Session):
    """Scans inventory and sends a notification if any item is below its threshold."""
    low_stock_items = session.exec(
        select(InventoryItem).where(InventoryItem.current_stock_level < InventoryItem.low_stock_threshold)
    ).all()
    
    if low_stock_items:
        item_names = ", ".join([item.name for item in low_stock_items])
        await broadcast_admin_notification(
            event="low_stock_alert",
            data={"message": f"Low stock warning: {item_names}"}
        )
        logging.warning(f"Low stock alert triggered for: {item_names}")

def deduct_stock_for_order(order_id: int, session: Session):
    """
    Deducts all relevant inventory items based on an order's final details.
    Triggered when an order is delivered.
    """
    order = session.get(Order, order_id)
    if not order or not order.confirmed_load_count:
        logging.warning(f"Inventory deduction skipped for Order {order_id}: No confirmed load count.")
        return

    settings = _get_settings_dict(session)
    loads = order.confirmed_load_count
    stains = session.exec(select(func.count(Image.id)).where(Image.order_id == order.id, Image.is_stain == True)).one()

    deductions = {
        "SOAP-001": loads * settings.get('usage_soap_kg_per_load', 0),
        "SOFT-001": loads * settings.get('usage_softener_l_per_load', 0),
        "STAIN-001": stains * settings.get('usage_stainremover_l_per_stain', 0),
        "BAG-001": settings.get('usage_bags_per_order', 0),
    }

    for sku, amount in deductions.items():
        if amount > 0:
            item = session.get(InventoryItem, sku)
            if item:
                item.current_stock_level -= amount
                session.add(item)
    
    session.commit()
    logging.info(f"Deducted inventory for Order {order_id}.")
    
    # Run the async check in the current event loop or a new one
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(check_for_low_stock(session))
    except RuntimeError:
        asyncio.run(check_for_low_stock(session))


def add_stock_from_withdrawal(withdrawal: Withdrawal, session: Session) -> str:
    """
    Adds purchased stock to inventory and recalculates the average cost.
    Returns a feedback message about the purchase price.
    """
    if not withdrawal.inventory_item_sku or not withdrawal.quantity_purchased:
        return ""

    item = session.get(InventoryItem, withdrawal.inventory_item_sku)
    if not item:
        logging.error(f"Could not find inventory item with SKU {withdrawal.inventory_item_sku} for withdrawal {withdrawal.id}")
        return "Error: Inventory item not found."

    purchase_price_per_unit = withdrawal.amount / withdrawal.quantity_purchased
    old_avg_cost = item.average_cost_per_unit
    old_stock = item.current_stock_level

    # Recalculate average cost
    if (old_stock + withdrawal.quantity_purchased) > 0:
        new_avg_cost = ((old_avg_cost * old_stock) + withdrawal.amount) / (old_stock + withdrawal.quantity_purchased)
        item.average_cost_per_unit = new_avg_cost

    item.current_stock_level += withdrawal.quantity_purchased
    session.add(item)
    session.commit()
    logging.info(f"Added {withdrawal.quantity_purchased} {item.unit_of_measurement} of {item.name} to inventory.")

    # Generate feedback
    if old_avg_cost > 0:
        if purchase_price_per_unit < old_avg_cost * 0.95:
            return f"Great deal! This purchase was cheaper than your average for {item.name}."
        elif purchase_price_per_unit > old_avg_cost * 1.05:
            return f"Note: This purchase was more expensive than your average for {item.name}."
    
    return "Inventory updated."