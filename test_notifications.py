#!/usr/bin/env python3
"""
Test script for notification system.
Run this to verify notifications are working.
"""
import asyncio
import os
from app.services.notifications import notification_service

async def test_notifications():
    """Test the notification system with sample data."""

    print("Testing notification system...")

    # Check configuration
    print(f"Email configured: {notification_service._can_send_email()}")
    print(f"Telegram configured: {notification_service._can_send_telegram()}")

    # Sample order data
    sample_order = {
        "id": 123,
        "external_id": "TEST-123",
        "customer_name": "Test Customer",
        "customer_phone": "+1234567890",
        "customer_address": "123 Test Street",
        "total_items": 5,
        "processing_option": "standard",
        "created_at": "2025-01-01T10:00:00Z",
        "ready_for_delivery_at": "2025-01-01T14:00:00Z"
    }

    print("\nTesting booking notification...")
    try:
        await notification_service.send_booking_notification(sample_order)
        print("[OK] Booking notification sent successfully")
    except Exception as e:
        print(f"[FAIL] Booking notification failed: {e}")

    print("\nTesting ready for delivery notification...")
    try:
        await notification_service.send_ready_for_delivery_notification(sample_order)
        print("[OK] Ready for delivery notification sent successfully")
    except Exception as e:
        print(f"[FAIL] Ready for delivery notification failed: {e}")

    print("\nNotification test completed!")

if __name__ == "__main__":
    # Load environment variables
    from dotenv import load_dotenv
    load_dotenv()

    asyncio.run(test_notifications())
