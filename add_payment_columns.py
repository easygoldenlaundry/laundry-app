#!/usr/bin/env python3
"""
Migration script to add payment-related columns to the order table.
Run this script to update the database schema.
"""
import sys
from sqlalchemy import text
from app.db import engine

def add_payment_columns():
    """Add the payment-related columns if they don't exist."""
    print("Checking database schema for payment columns...")

    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='order'
            AND column_name IN ('payment_status', 'payment_method', 'paystack_reference')
        """))
        existing_columns = [row[0] for row in result]

        if all(col in existing_columns for col in ['payment_status', 'payment_method', 'paystack_reference']):
            print("All payment columns already exist! No migration needed.")
            return True

        # Add missing columns
        try:
            if 'payment_status' not in existing_columns:
                print("Adding payment_status column...")
                conn.execute(text("ALTER TABLE \"order\" ADD COLUMN payment_status VARCHAR(50) DEFAULT 'pending'"))
                conn.commit()
                print("payment_status column added!")

            if 'payment_method' not in existing_columns:
                print("Adding payment_method column...")
                conn.execute(text("ALTER TABLE \"order\" ADD COLUMN payment_method VARCHAR(50) NULL"))
                conn.commit()
                print("payment_method column added!")

            if 'paystack_reference' not in existing_columns:
                print("Adding paystack_reference column...")
                conn.execute(text("ALTER TABLE \"order\" ADD COLUMN paystack_reference VARCHAR(255) NULL"))
                conn.commit()
                print("paystack_reference column added!")

            print("Payment columns migration completed successfully!")
            return True

        except Exception as e:
            print(f"Migration failed: {e}")
            conn.rollback()
            return False

if __name__ == "__main__":
    try:
        success = add_payment_columns()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
