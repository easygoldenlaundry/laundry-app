#!/usr/bin/env python3
"""
Script to fix missing Driver record for user ID 4
"""
import sys
import os
sys.path.append('.')

from app.db import get_session
from app.models import Driver, User
from sqlmodel import select

def fix_missing_driver_record():
    session = next(get_session())
    
    print("=== CHECKING CURRENT STATE ===")
    
    # Check if user ID 4 exists
    user_4 = session.get(User, 4)
    if not user_4:
        print("ERROR: User ID 4 does not exist!")
        return False
    
    print(f"User ID 4: {user_4.username} ({user_4.display_name}) - Role: {user_4.role}")
    
    # Check if Driver record exists for user ID 4
    existing_driver = session.exec(select(Driver).where(Driver.user_id == 4)).first()
    if existing_driver:
        print(f"Driver record already exists: ID {existing_driver.id}, Status: {existing_driver.status}")
        return True
    
    print("Driver record is missing for user ID 4. Creating it...")
    
    # Create the missing Driver record
    new_driver = Driver(user_id=4, status="idle")
    session.add(new_driver)
    session.commit()
    session.refresh(new_driver)
    
    print(f"SUCCESS: Created Driver record with ID {new_driver.id} for user ID 4")
    
    # Verify the creation
    driver = session.exec(select(Driver).where(Driver.user_id == 4)).first()
    if driver:
        print(f"VERIFIED: Driver ID {driver.id} exists for user ID 4")
        return True
    else:
        print("ERROR: Failed to create Driver record")
        return False

if __name__ == "__main__":
    try:
        success = fix_missing_driver_record()
        if success:
            print("\n✅ Driver record fixed successfully!")
        else:
            print("\n❌ Failed to fix Driver record")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

