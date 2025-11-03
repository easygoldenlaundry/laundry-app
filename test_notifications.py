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

    # Check configuration and debug
    print(f"Email configured: {notification_service._can_send_email()}")
    print(f"Telegram configured: {notification_service._can_send_telegram()}")
    print(f"SMTP username: {notification_service.smtp_username}")
    print(f"SMTP password: {'***' if notification_service.smtp_password else None}")
    print(f"Notification email: {notification_service.notification_email}")
    print(f"Telegram bot token: {notification_service.telegram_bot_token[:15] + '***' if notification_service.telegram_bot_token else None}")
    print(f"Telegram chat ID: {notification_service.telegram_chat_id}")
    print(f"Telegram bot initialized: {notification_service.telegram_bot is not None}")

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

    # Note: Using environment variables from .env file
    # If you need to override for testing, uncomment the lines below:
    # import os
    # os.environ["SMTP_SERVER"] = "smtp.gmail.com"
    # os.environ["SMTP_PORT"] = "587"
    # os.environ["SMTP_USERNAME"] = "Siya.jan.k@gmail.com"
    # os.environ["SMTP_PASSWORD"] = "qtxtlsgolhulxghb"
    # os.environ["NOTIFICATION_EMAIL"] = "test@example.com"
    # os.environ["TELEGRAM_BOT_TOKEN"] = "8290597117:AAHtCN1QiVEsdmYVliAgd-KXgOlNLhwV"
    # os.environ["TELEGRAM_CHAT_ID"] = "1139264248"

    # Reload notification service config after loading env vars
    from app.services.notifications import notification_service
    notification_service.reload_config()

    asyncio.run(test_notifications())
