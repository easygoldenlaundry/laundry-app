# app/routes/debug.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db import get_session
from app.services.notifications import notification_service
import asyncio

router = APIRouter(prefix="/debug", tags=["Debug"])

@router.get("/test-notification")
async def test_notification():
    """Test notification system."""
    try:
        # Check configuration
        email_configured = notification_service._can_send_email()
        telegram_configured = notification_service._can_send_telegram()

        # Test data
        test_order = {
            "id": 999,
            "external_id": "TEST-999",
            "customer_name": "Test Customer",
            "customer_phone": "+1234567890",
            "customer_address": "123 Test Street",
            "total_items": 3,
            "processing_option": "standard",
            "created_at": "2025-01-01T10:00:00Z"
        }

        # Send test notifications
        email_task = asyncio.create_task(notification_service.send_booking_notification(test_order))
        telegram_task = asyncio.create_task(notification_service.send_ready_for_delivery_notification(test_order))

        await asyncio.gather(email_task, telegram_task, return_exceptions=True)

        return {
            "status": "Test notifications sent",
            "email_configured": email_configured,
            "telegram_configured": telegram_configured,
            "message": "Check your email and Telegram for test messages"
        }

    except Exception as e:
        return {
            "status": "Error",
            "error": str(e),
            "email_configured": notification_service._can_send_email(),
            "telegram_configured": notification_service._can_send_telegram()
        }

@router.get("/env-check")
async def check_environment():
    """Check environment variables."""
    import os
    return {
        "SMTP_USERNAME": os.getenv("SMTP_USERNAME"),
        "NOTIFICATION_EMAIL": os.getenv("NOTIFICATION_EMAIL"),
        "TELEGRAM_BOT_TOKEN": "***" + os.getenv("TELEGRAM_BOT_TOKEN")[-5:] if os.getenv("TELEGRAM_BOT_TOKEN") else None,
        "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID"),
        "email_configured": notification_service._can_send_email(),
        "telegram_configured": notification_service._can_send_telegram()
    }
