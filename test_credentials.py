#!/usr/bin/env python3
"""
Test your email and Telegram credentials before deploying.
"""
import smtplib
from email.mime.text import MIMEText
from telegram import Bot
import asyncio

# Your credentials - replace these with your actual values
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USERNAME = "Siya.jan.k@gmail.com"
SMTP_PASSWORD = "qtxtlsgolhulxghb"

TELEGRAM_BOT_TOKEN = "8290597117:AAHtCN1QiVEsdmYVliAgd-KXgOlNLhwV5k4"
TELEGRAM_CHAT_ID = "1139264248"

async def test_email():
    """Test email configuration."""
    try:
        msg = MIMEText("Test email from Laundry App")
        msg['From'] = SMTP_USERNAME
        msg['To'] = SMTP_USERNAME
        msg['Subject'] = "Test Notification"

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.sendmail(SMTP_USERNAME, SMTP_USERNAME, msg.as_string())
        server.quit()

        print("[OK] Email test: SUCCESS")
        return True
    except Exception as e:
        print(f"[FAIL] Email test: FAILED - {e}")
        return False

async def test_telegram():
    """Test Telegram configuration."""
    try:
        bot = Bot(token=TELEGRAM_BOT_TOKEN)
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text="Test message from Laundry App notification system!"
        )
        print("[OK] Telegram test: SUCCESS")
        return True
    except Exception as e:
        print(f"[FAIL] Telegram test: FAILED - {e}")
        return False

async def main():
    """Run all tests."""
    print("Testing your notification credentials...\n")

    email_ok = await test_email()
    telegram_ok = await test_telegram()

    print(f"\nResults: Email {'[OK]' if email_ok else '[FAIL]'}, Telegram {'[OK]' if telegram_ok else '[FAIL]'}")

    if email_ok and telegram_ok:
        print("\n[SUCCESS] All tests passed! Your notifications are ready to deploy!")
    else:
        print("\n[WARNING] Some tests failed. Please check your credentials and try again.")

if __name__ == "__main__":
    asyncio.run(main())
