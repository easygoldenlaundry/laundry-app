import requests
import json

# Test login to get JWT token
login_url = "http://localhost:8000/api/auth/token/mobile"
login_data = {
    "username": "Easy@gmail.com",
    "password": "password"
}

print("Logging in...")
response = requests.post(login_url, json=login_data)
if response.status_code == 200:
    token_data = response.json()
    token = token_data["access_token"]
    print(f"Got token: {token[:50]}...")

    # Test the my-orders endpoint
    orders_url = "http://localhost:8000/api/orders/my-orders"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    print("Testing /api/orders/my-orders endpoint...")
    orders_response = requests.get(orders_url, headers=headers)
    print(f"Status code: {orders_response.status_code}")
    if orders_response.status_code == 200:
        orders = orders_response.json()
        print(f"Got {len(orders)} orders:")
        for order in orders[:3]:  # Show first 3 orders
            print(f"  Order {order['id']}: status={order['status']}, cost={order['total_cost']}, loads={order['number_of_loads']}")
    else:
        print(f"Error: {orders_response.text}")
else:
    print(f"Login failed: {response.status_code} - {response.text}")
