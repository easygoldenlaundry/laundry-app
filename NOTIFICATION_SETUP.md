# Notification System Setup

This document explains how to set up email and Telegram notifications for order events.

## Environment Variables Required

Add these environment variables to your `.env` file:

```bash
# --- NOTIFICATION SETTINGS ---
# Email configuration (for Gmail, use smtp.gmail.com:587)
SMTP_SERVER="smtp.gmail.com"
SMTP_PORT="587"
SMTP_USERNAME="your-email@gmail.com"
SMTP_PASSWORD="your-app-password"

# Email address where notifications will be sent
NOTIFICATION_EMAIL="your-notification-email@gmail.com"

# Telegram configuration
TELEGRAM_BOT_TOKEN="your-telegram-bot-token"
TELEGRAM_CHAT_ID="your-telegram-chat-id"
```

## Setup Instructions

### 1. Email Setup (Gmail)

1. **Enable 2-Factor Authentication** on your Gmail account
2. **Generate an App Password**:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate a password for "Mail"
   - Use this password as `SMTP_PASSWORD`

3. **Configure Environment Variables**:
   - `SMTP_USERNAME`: Your Gmail address
   - `SMTP_PASSWORD`: The app password (not your regular password)
   - `NOTIFICATION_EMAIL`: Email address where you want to receive notifications

### 2. Telegram Setup

1. **Create a Telegram Bot**:
   - Message @BotFather on Telegram
   - Send `/newbot` and follow the instructions
   - Save the bot token you receive

2. **Get Your Chat ID**:
   - Start a conversation with your bot
   - Send a message to the bot
   - Visit `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Find your chat ID in the response

3. **Configure Environment Variables**:
   - `TELEGRAM_BOT_TOKEN`: The token from BotFather
   - `TELEGRAM_CHAT_ID`: Your chat ID from the API call

## What Gets Notified

The system will send notifications for:

1. **New Order Booked**: When a customer books an order (status becomes "Created")
2. **Order Ready for Delivery**: When an order passes QA and becomes ready for delivery (status becomes "ReadyForDelivery")

Both email and Telegram notifications are sent simultaneously if configured.

## Testing

After setup, you can test the notifications by:
1. Creating a new order through the web or mobile app
2. Processing an order through the QA station to make it ready for delivery

## Troubleshooting

- **Email not working**: Check your Gmail app password and SMTP settings
- **Telegram not working**: Verify your bot token and chat ID
- **Notifications not sent**: Check application logs for error messages

## Security Notes

- Never commit your `.env` file to version control
- Use app passwords instead of regular Gmail passwords
- Keep your Telegram bot token secure
