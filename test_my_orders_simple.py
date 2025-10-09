import sys
import os
sys.path.append('.')

from app.db import get_session
from app.models import User, Customer, Order, FinanceEntry, Driver
from app.auth import create_access_token

def test_my_orders_logic():
    # Get a session
    session = next(get_session())

    # Find a customer user
    customer_user = session.query(User).filter(User.role == "customer").first()
    if not customer_user:
        print("No customer user found!")
        return

    print(f"Testing with user: {customer_user.username} (ID: {customer_user.id})")

    # Get customer profile
    customer = session.query(Customer).filter(Customer.user_id == customer_user.id).first()
    if not customer:
        print("No customer profile found!")
        return

    print(f"Customer profile: {customer.full_name} (ID: {customer.id})")

    # Check how many orders this customer has
    orders = session.query(Order).filter(Order.customer_id == customer.id).order_by(Order.created_at.desc()).all()
    print(f"Customer has {len(orders)} orders in database")

    response_orders = []
    for order in orders:
        # Calculate total cost from finance entries
        total_cost = 0.0
        finance_entries = session.query(FinanceEntry).filter(
            FinanceEntry.order_id == order.id,
            FinanceEntry.entry_type == 'revenue'
        ).all()
        for entry in finance_entries:
            total_cost += entry.amount

        # Get driver info if assigned
        driver_name = None
        driver_id = None
        if order.assigned_driver_id:
            driver = session.query(Driver).filter(Driver.id == order.assigned_driver_id).first()
            if driver:
                driver_user = session.get(User, driver.user_id)
                if driver_user:
                    driver_name = driver_user.display_name
                    driver_id = driver.id

        # Use confirmed_load_count if available, otherwise basket_count, otherwise 0
        number_of_loads = order.confirmed_load_count or order.basket_count or 0

        response_orders.append({
            "id": order.id,
            "customer_id": order.customer_id,
            "status": order.status,
            "total_cost": total_cost,
            "number_of_loads": number_of_loads,
            "created_at": order.created_at.isoformat(),
            "driver_name": driver_name,
            "driver_id": driver_id
        })

    print(f"Generated response with {len(response_orders)} orders:")
    for order in response_orders[:3]:  # Show first 3
        print(f"  Order {order['id']}: status={order['status']}, cost={order['total_cost']}, loads={order['number_of_loads']}, driver={order.get('driver_name', 'None')}")

if __name__ == "__main__":
    test_my_orders_logic()
