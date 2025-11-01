# app/services/notifications.py
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from telegram import Bot
from telegram.error import TelegramError
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self):
        # Email configuration
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.notification_email = os.getenv("NOTIFICATION_EMAIL")  # Where notifications are sent

        # Telegram configuration
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

        # Initialize Telegram bot
        self.telegram_bot = Bot(token=self.telegram_bot_token) if self.telegram_bot_token else None

    async def send_booking_notification(self, order_data: dict):
        """Send notification when a new order is booked."""
        subject = f"New Order Booked - {order_data.get('external_id', 'Unknown')}"
        message = f"""
New order has been booked!

Order Details:
- Order ID: {order_data.get('id')}
- External ID: {order_data.get('external_id')}
- Customer: {order_data.get('customer_name')}
- Phone: {order_data.get('customer_phone')}
- Address: {order_data.get('customer_address')}
- Total Items: {order_data.get('total_items', 0)}
- Processing Option: {order_data.get('processing_option', 'standard')}
- Created At: {order_data.get('created_at')}

Status: Created (waiting for driver pickup)
"""

        await self._send_notifications(subject, message)

    async def send_ready_for_delivery_notification(self, order_data: dict):
        """Send notification when an order is ready for delivery."""
        subject = f"Order Ready for Delivery - {order_data.get('external_id', 'Unknown')}"
        message = f"""
Order is now ready for delivery!

Order Details:
- Order ID: {order_data.get('id')}
- External ID: {order_data.get('external_id')}
- Customer: {order_data.get('customer_name')}
- Phone: {order_data.get('customer_phone')}
- Address: {order_data.get('customer_address')}
- Total Items: {order_data.get('total_items', 0)}
- Processing Option: {order_data.get('processing_option', 'standard')}
- Ready At: {order_data.get('ready_for_delivery_at')}

Status: Ready for Delivery (customer can now request delivery)
"""

        await self._send_notifications(subject, message)

    async def _send_notifications(self, subject: str, message: str):
        """Send both email and Telegram notifications."""
        tasks = []

        # Send email notification
        if self._can_send_email():
            tasks.append(self._send_email(subject, message))

        # Send Telegram notification
        if self._can_send_telegram():
            tasks.append(self._send_telegram(message))

        # Execute all notifications concurrently
        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except Exception as e:
                logger.error(f"Failed to send notifications: {e}")

    def _can_send_email(self) -> bool:
        """Check if email configuration is complete."""
        return all([
            self.smtp_username,
            self.smtp_password,
            self.notification_email
        ])

    def _can_send_telegram(self) -> bool:
        """Check if Telegram configuration is complete."""
        return all([
            self.telegram_bot_token,
            self.telegram_chat_id,
            self.telegram_bot
        ])

    async def _send_email(self, subject: str, message: str):
        """Send email notification."""
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.smtp_username
            msg['To'] = self.notification_email
            msg['Subject'] = subject

            # Add body
            msg.attach(MIMEText(message, 'plain'))

            # Create SMTP connection
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)

            # Send email
            text = msg.as_string()
            server.sendmail(self.smtp_username, self.notification_email, text)
            server.quit()

            logger.info(f"Email notification sent successfully to {self.notification_email}")

        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            raise

    async def _send_telegram(self, message: str):
        """Send Telegram notification."""
        try:
            await self.telegram_bot.send_message(
                chat_id=self.telegram_chat_id,
                text=message,
                parse_mode='Markdown'
            )
            logger.info(f"Telegram notification sent successfully to chat {self.telegram_chat_id}")

        except TelegramError as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram notification: {e}")
            raise

# Global notification service instance
notification_service = NotificationService()
