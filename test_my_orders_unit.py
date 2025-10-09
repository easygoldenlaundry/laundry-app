import sys
import os
sys.path.append('.')

from fastapi.testclient import TestClient
from app.main import fastapi_app
from app.db import get_session
from app.models import User, Customer, Order, FinanceEntry
from app.auth import get_password_hash, create_access_token

# Create test client
client = TestClient(fastapi_app)

def test_my_orders_endpoint():
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
    orders = session.query(Order).filter(Order.customer_id == customer.id).all()
    print(f"Customer has {len(orders)} orders in database")

    # Create a JWT token for this user
    token = create_access_token(data={"sub": customer_user.username})

    # Test the endpoint
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    response = client.get("/api/orders/my-orders", headers=headers)
    print(f"Response status: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"Got {len(data)} orders from API:")
        for order in data[:3]:  # Show first 3
            print(f"  Order {order['id']}: status={order['status']}, cost={order['total_cost']}, loads={order['number_of_loads']}, driver={order.get('driver_name', 'None')}")
    else:
        print(f"Error response: {response.text}")

if __name__ == "__main__":
    test_my_orders_endpoint()
