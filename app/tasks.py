# app/tasks.py
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, delete

from app.db import get_engine
from app.models import Message, Setting

async def delete_old_messages_periodically():
    """A background task that runs once a day to delete messages older than 3 days."""
    logging.info("--- Starting background old message cleaner ---")
    engine = get_engine()
    
    while True:
        try:
            with Session(engine) as session:
                three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
                statement = delete(Message).where(Message.timestamp < three_days_ago)
                results = session.exec(statement)
                session.commit()
                logging.info(f"Cleaned up {results.rowcount} old chat messages.")
        except Exception as e:
            logging.error(f"Error in message cleaner loop: {e}", exc_info=True)

        # Sleep for 24 hours
        await asyncio.sleep(60 * 60 * 24)

async def reset_monthly_trackers():
    """
    A background task that checks daily if it's the 1st of the month,
    and if so, resets the monthly financial trackers.
    """
    logging.info("--- Starting background monthly tracker reset task ---")
    engine = get_engine()
    last_reset_month = -1

    while True:
        try:
            now = datetime.now(timezone.utc)
            current_month = now.month

            # Check if it's the first day of a new month that we haven't reset yet
            if now.day == 1 and current_month != last_reset_month:
                logging.info(f"It's the 1st of month {current_month}. Resetting monthly finance trackers.")
                with Session(engine) as session:
                    elec_tracker = session.get(Setting, "monthly_tracker_electricity_kwh")
                    if elec_tracker:
                        elec_tracker.value = "0"
                        session.add(elec_tracker)
                        
                    session.commit()
                    last_reset_month = current_month
                    logging.info("Monthly trackers have been reset.")
            else:
                logging.debug("Not the 1st of the month, skipping tracker reset.")

        except Exception as e:
            logging.error(f"Error in monthly tracker reset loop: {e}", exc_info=True)

        # Sleep for 24 hours
        await asyncio.sleep(60 * 60 * 24)