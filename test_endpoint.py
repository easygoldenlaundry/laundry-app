import requests
import json

# First, get an admin token
try:
    login_response = requests.post('http://localhost:8000/api/auth/token/mobile', json={
        "username": "admin",
        "password": "admin"
    })
    print(f'Login status: {login_response.status_code}')
    if login_response.status_code == 200:
        token_data = login_response.json()
        token = token_data.get('access_token')
        print(f'Got token: {token[:20]}...')

        # Now test the orders endpoint
        response = requests.get('http://localhost:8000/api/admin/orders/active?hub_id=1',
                               headers={'Authorization': f'Bearer {token}'})
        print(f'Orders endpoint status: {response.status_code}')
        print(f'Response content: {response.text[:500]}')  # First 500 chars
        if response.status_code == 200:
            try:
                data = response.json()
                print(f'Number of orders: {len(data)}')
                if data:
                    print(f'First order keys: {list(data[0].keys())}')
                    print(f'First order status: {data[0].get("status")}')
                else:
                    print('No orders returned')
            except json.JSONDecodeError as je:
                print(f'JSON decode error: {je}')
        else:
            print(f'Error: {response.text}')
    else:
        print(f'Login failed: {login_response.text}')
except Exception as e:
    print(f'Error: {e}')
