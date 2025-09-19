# app/seed_db.py
import os
import uuid
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from app.auth import get_password_hash
from app.db import create_db_and_tables, get_engine
from app.models import User, Station, Machine, Order, Item, Bag, Setting, Customer

def seed_database():
    """
    Idempotent seed script. Creates tables and populates with sample data
    only if the tables are empty.
    """
    print("--- Starting database seed ---")
    engine = get_engine()
    
    # Create tables if they don't exist
    create_db_and_tables()

    with Session(engine) as session:
        # Check if settings exist
        setting_check = session.exec(select(Setting)).first()
        if not setting_check:
            print("No settings found. Creating default settings...")
            settings = [
                Setting(key="price_per_load", value="150.00"),
                Setting(key="express_delivery_hours", value="5"),
                Setting(key="next_day_delivery_hours", value="24"),
                Setting(key="wash_cycle_time_seconds", value="1800"),
                Setting(key="dry_cycle_time_seconds", value="2400"),
                Setting(key="fold_cycle_time_seconds", value="300"),
                Setting(key="hub_intake_qr_code", value="HUB1-INTAKE-SECRET"),
                Setting(key="driver_hub_delivery_qr", value="DRIVER-DELIVERS-TO-HUB"),
                Setting(key="driver_hub_pickup_qr", value="DRIVER-PICKS-UP-FROM-HUB"),
                Setting(key="washing_machine_count", value="1"),
                Setting(key="drying_machine_count", value="1"),
                Setting(key="folding_machine_count", value="1"),
            ]
            session.add_all(settings)
            session.commit()
        else:
            print("Settings already exist. Skipping creation.")

        # Check if users exist
        user_check = session.exec(select(User)).first()
        if not user_check:
            print("No users found. Creating default users...")
            admin_user = os.getenv("ADMIN_USER", "admin")
            admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
            admin_pass = os.getenv("ADMIN_PASSWORD", "admin")
            
            # Create a guaranteed active admin user
            user_admin = User(
                username=admin_user,
                email=admin_email,
                hashed_password=get_password_hash(admin_pass),
                role="admin",
                display_name="Admin User",
                is_active=True # Admin is always active
            )
            
            # Create a sample driver user that is now ACTIVE by default for easier testing.
            user_driver = User(
                username="driver1",
                email="driver1@example.com",
                hashed_password=get_password_hash("password"),
                role="driver",
                display_name="Sample Driver",
                is_active=True
            )
            
            # --- THIS IS THE FIX: Grant default permissions to the sample staff user ---
            user_staff = User(
                username="staff1",
                email="staff1@example.com",
                hashed_password=get_password_hash("password"),
                role="staff",
                display_name="Hub Staff Member",
                is_active=True,
                # Give this user access to all stations for easy testing
                allowed_stations="hub_intake,imaging,pretreat,washing,drying,folding,qa_station"
            )
            session.add(user_admin)
            session.add(user_driver)
            session.add(user_staff)
            session.commit()
            print(f"-> Created ADMIN user: {user_admin.username} (active: {user_admin.is_active})")
            print(f"-> Created DRIVER user: {user_driver.username} (active: {user_driver.is_active})")
            print(f"-> Created STAFF user: {user_staff.username} (active: {user_staff.is_active}) with full station access.")
        else:
            print("Users already exist. Skipping creation.")


        # Check if stations exist
        station_check = session.exec(select(Station)).first()
        if not station_check:
            print("No stations found. Creating stations for Hub 1...")
            stations = [
                Station(hub_id=1, type="imaging", capacity=5, title="Imaging Station"),
                Station(hub_id=1, type="Pretreat", capacity=5, title="Pretreat Station"),
                Station(hub_id=1, type="washing", capacity=10, title="Washing Station"),
                Station(hub_id=1, type="drying", capacity=10, title="Drying Station"),
                Station(hub_id=1, type="folding", capacity=8, title="Folding Station"),
                Station(hub_id=1, type="qa", capacity=5, title="Quality Assurance"),
            ]
            session.add_all(stations)
            session.commit()
            
            # Create Machines based on default settings
            settings_dict = {s.key: s.value for s in session.exec(select(Setting)).all()}
            wash_station_id = session.exec(select(Station).where(Station.type == "washing")).one().id
            dry_station_id = session.exec(select(Station).where(Station.type == "drying")).one().id
            fold_station_id = session.exec(select(Station).where(Station.type == "folding")).one().id
            
            for _ in range(int(settings_dict.get("washing_machine_count", 1))):
                session.add(Machine(station_id=wash_station_id, type="washer", cycle_time_seconds=int(settings_dict.get("wash_cycle_time_seconds", 1800))))
            for _ in range(int(settings_dict.get("drying_machine_count", 1))):
                session.add(Machine(station_id=dry_station_id, type="dryer", cycle_time_seconds=int(settings_dict.get("dry_cycle_time_seconds", 2400))))
            for _ in range(int(settings_dict.get("folding_machine_count", 1))):
                 session.add(Machine(station_id=fold_station_id, type="folder", cycle_time_seconds=int(settings_dict.get("fold_cycle_time_seconds", 300))))
            
            session.commit()
        else:
            print("Stations already exist. Skipping creation.")


        # Check if orders exist
        order_check = session.exec(select(Order)).first()
        if not order_check:
            print("No orders found. Creating 3 sample orders...")
            orders_data = [
                {"name": "Alice Wonderland"},
                {"name": "Bob Builder"},
                {"name": "Charlie Chocolate"},
            ]

            for i, data in enumerate(orders_data):
                token = str(uuid.uuid4())
                
                sla = None
                if i == 0:
                    sla = datetime.now(timezone.utc) + timedelta(minutes=1)
                    print(f"  - Setting test SLA for '{data['name']}' to: {sla}")

                order = Order(
                    external_id=f"ext_{token[:6]}",
                    tracking_token=token,
                    customer_name=data["name"],
                    customer_phone="123-555-0101",
                    customer_address="123 Main St, Anytown",
                    total_items=0, 
                    status="Created",
                    sla_deadline=sla
                )
                session.add(order)
                session.commit()
                session.refresh(order)

                default_bag = Bag(order_id=order.id, bag_code=f"BAG-ORDER{order.id}")
                session.add(default_bag)
                session.commit()

                print(f"  - Created Order ID: {order.id} with status '{order.status}' and Bag Code '{default_bag.bag_code}'")
        else:
            print("Orders already exist. Skipping creation.")

    print("--- Database seed finished ---")

if __name__ == "__main__":
    seed_database()