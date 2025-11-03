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
        self._load_config()

    def _load_config(self):
        """Load configuration from environment variables."""
        # Email configuration
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_username = os.getenv("SMTP_USERNAME")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.notification_email = os.getenv("NOTIFICATION_EMAIL")  # Where notifications are sent

        # Telegram configuration
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        # Ensure chat_id is string (Telegram API accepts both string and int)
        if self.telegram_chat_id and not isinstance(self.telegram_chat_id, str):
            self.telegram_chat_id = str(self.telegram_chat_id)

        # Initialize Telegram bot
        self.telegram_bot = Bot(token=self.telegram_bot_token) if self.telegram_bot_token else None

        logger.info(f"NotificationService configured - Email: {self._can_send_email()}, Telegram: {self._can_send_telegram()}")

    def reload_config(self):
        """Reload configuration from environment variables (useful after dotenv loading)."""
        self._load_config()

    async def send_booking_notification(self, order_data: dict):
        """Send notification when a new order is booked."""
        logger.info(f"Sending booking notification for order {order_data.get('id')}")

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
        logger.info(f"Sending ready for delivery notification for order {order_data.get('id')}")

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
        logger.info(f"Sending notifications - Email configured: {self._can_send_email()}, Telegram configured: {self._can_send_telegram()}")

        tasks = []

        # Send email notification
        if self._can_send_email():
            logger.info("Adding email notification task")
            tasks.append(self._send_email(subject, message))
        else:
            logger.warning("Email not configured - skipping email notification")

        # Send Telegram notification
        if self._can_send_telegram():
            logger.info("Adding Telegram notification task")
            tasks.append(self._send_telegram(message))
        else:
            logger.warning("Telegram not configured - skipping Telegram notification")

        # Execute all notifications concurrently
        if tasks:
            try:
                logger.info(f"Executing {len(tasks)} notification tasks")
                results = await asyncio.gather(*tasks, return_exceptions=True)
                success_count = sum(1 for r in results if not isinstance(r, Exception))
                logger.info(f"Notification tasks completed: {success_count}/{len(tasks)} successful")
            except Exception as e:
                logger.error(f"Failed to send notifications: {e}")
        else:
            logger.warning("No notification methods configured - skipping all notifications")

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
            # Try sending with Markdown first, fallback to plain text if it fails
            try:
                await self.telegram_bot.send_message(
                    chat_id=self.telegram_chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
            except TelegramError as e:
                if 'BadRequest' in str(e) and ('parse' in str(e).lower() or 'markdown' in str(e).lower()):
                    # Fallback to plain text if Markdown parsing fails
                    logger.warning(f"Markdown parsing failed, sending as plain text: {e}")
                    await self.telegram_bot.send_message(
                        chat_id=self.telegram_chat_id,
                        text=message,
                        parse_mode=None
                    )
                else:
                    raise
            logger.info(f"Telegram notification sent successfully to chat {self.telegram_chat_id}")

        except TelegramError as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram notification: {e}")
            raise

# Global notification service instance
notification_service = NotificationService()
