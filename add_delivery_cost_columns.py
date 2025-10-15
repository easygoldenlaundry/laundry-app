#!/usr/bin/env python3
"""
Migration script to add delivery_cost and delivery_distance_km columns to the order table.
Run this script to update the production database schema.
"""
import sys
from sqlalchemy import text
from app.db import engine

def add_columns():
    """Add the new delivery cost columns if they don't exist."""
    print("🔄 Checking database schema...")
    
    with engine.connect() as conn:
        # Check if columns already exist
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='order' 
            AND column_name IN ('delivery_cost', 'delivery_distance_km')
        """))
        existing_columns = [row[0] for row in result]
        
        if 'delivery_cost' in existing_columns and 'delivery_distance_km' in existing_columns:
            print("✅ Columns already exist! No migration needed.")
            return True
        
        # Add missing columns
        try:
            if 'delivery_cost' not in existing_columns:
                print("➕ Adding delivery_cost column...")
                conn.execute(text("ALTER TABLE \"order\" ADD COLUMN delivery_cost FLOAT NULL"))
                conn.commit()
                print("✅ delivery_cost column added!")
            
            if 'delivery_distance_km' not in existing_columns:
                print("➕ Adding delivery_distance_km column...")
                conn.execute(text("ALTER TABLE \"order\" ADD COLUMN delivery_distance_km FLOAT NULL"))
                conn.commit()
                print("✅ delivery_distance_km column added!")
            
            print("🎉 Migration completed successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            conn.rollback()
            return False

if __name__ == "__main__":
    try:
        success = add_columns()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)

