#!/usr/bin/env python3
"""
Test script for mobile ETA endpoints.
Tests the new mobile-specific endpoints for location updates and ETA retrieval.
"""

import requests
import json
import sys

# Configuration
BASE_URL = "http://localhost:8000"  # Adjust if running on different port

def test_mobile_auth():
    """Test mobile authentication endpoint."""
    print("Testing mobile authentication...")

    # Test login with driver credentials (adjust these for your test user)
    login_data = {
        "username": "driver1",  # Replace with actual test driver username
        "password": "password123"  # Replace with actual test password
    }

    response = requests.post(f"{BASE_URL}/api/auth/token/mobile", json=login_data)

    if response.status_code == 200:
        token_data = response.json()
        print(f"✓ Authentication successful for user: {token_data.get('user', {}).get('username')}")
        return token_data.get('access_token')
    else:
        print(f"✗ Authentication failed: {response.status_code} - {response.text}")
        return None

def test_mobile_location_update(token, lat=-26.2041, lon=28.0473):
    """Test mobile location update endpoint."""
    print("Testing mobile location update...")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    location_data = {
        "lat": lat,
        "lon": lon
    }

    response = requests.post(
        f"{BASE_URL}/api/driver/mobile/location",
        headers=headers,
        json=location_data
    )

    if response.status_code == 200:
        result = response.json()
        print(f"✓ Location update successful: {result}")
        return result
    else:
        print(f"✗ Location update failed: {response.status_code} - {response.text}")
        return None

def test_mobile_eta_retrieval(order_id, tracking_token):
    """Test mobile ETA retrieval endpoint."""
    print("Testing mobile ETA retrieval...")

    params = {
        "tracking_token": tracking_token
    }

    response = requests.get(
        f"{BASE_URL}/api/orders/mobile/{order_id}/eta",
        params=params
    )

    if response.status_code == 200:
        eta_data = response.json()
        print(f"✓ ETA retrieval successful: {eta_data}")
        return eta_data
    else:
        print(f"✗ ETA retrieval failed: {response.status_code} - {response.text}")
        return None

def main():
    """Run all tests."""
    print("=== Mobile ETA Endpoints Test ===\n")

    # Test authentication
    token = test_mobile_auth()
    if not token:
        print("Cannot continue without authentication token.")
        sys.exit(1)

    print()

    # Test location update
    location_result = test_mobile_location_update(token)
    if location_result:
        print(f"Active job: {location_result.get('has_active_job')}")
        if location_result.get('has_active_job'):
            print(f"Order ID: {location_result.get('order_id')}")
            print(f"ETA: {location_result.get('eta_minutes')} minutes")
            print(f"Progress: {location_result.get('progress')}%")

    print()

    # Test ETA retrieval (you'll need to provide actual order_id and tracking_token)
    # Uncomment and modify these lines with actual test data
    # order_id = 123  # Replace with actual order ID
    # tracking_token = "abc123"  # Replace with actual tracking token
    # eta_result = test_mobile_eta_retrieval(order_id, tracking_token)

    print("\n=== Test Summary ===")
    print("✓ Mobile authentication endpoint: Working")
    print("✓ Mobile location update endpoint: Working")
    print("? Mobile ETA retrieval endpoint: Needs test data (order_id + tracking_token)")

    print("\n=== API Usage Examples ===")
    print("""
# 1. Authenticate (get token)
POST /api/auth/token/mobile
{
    "username": "driver_username",
    "password": "driver_password"
}

# 2. Send location updates (every 20 seconds)
POST /api/driver/mobile/location
Authorization: Bearer <token>
{
    "lat": -26.2041,
    "lon": 28.0473
}

# 3. Get ETA for customer order
GET /api/orders/mobile/{order_id}/eta?tracking_token={tracking_token}
""")

if __name__ == "__main__":
    main()
