#!/usr/bin/env python3
"""
Database migration script to add processing_option column to order table.
Run this script once in production to add the missing column.
"""

import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL environment variable not set.")
    sys.exit(1)

def add_processing_option_column():
    """Add processing_option column to order table."""
    engine = create_engine(DATABASE_URL)

    try:
        with engine.begin() as conn:
            # Check if column already exists
            result = conn.execute(text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'order' AND column_name = 'processing_option'
            """))

            if result.fetchone():
                print("Column processing_option already exists.")
                return

            # Add the column with default value
            print("Adding processing_option column to order table...")
            conn.execute(text("""
                ALTER TABLE "order"
                ADD COLUMN processing_option VARCHAR(255) DEFAULT 'standard'
            """))

            print("Successfully added processing_option column!")

    except Exception as e:
        print(f"Error adding column: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("Starting database migration...")
    add_processing_option_column()
    print("Migration completed successfully!")
