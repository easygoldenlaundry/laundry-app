# app/seed_db.py
import os
import uuid
import secrets
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from app.auth import get_password_hash
from app.db import create_db_and_tables, get_engine
from app.models import User, Station, Machine, Order, Item, Bag, Setting, Customer, InventoryItem

def seed_database():
    """
    Idempotent seed script. Creates tables and populates with sample data
    only if the tables are empty.
    """
    print("--- Starting database seed ---")
    engine = get_engine()
    
    create_db_and_tables()

    with Session(engine) as session:
        setting_check = session.exec(select(Setting)).first()
        if not setting_check:
            print("No settings found. Creating default settings...")
            # --- THIS IS THE FIX: Pre-calculate the monthly electricity budget ---
            cost_base_electricity_monthly = 500.0
            cost_electricity_kwh = 3.91
            monthly_budget_kwh = cost_base_electricity_monthly / cost_electricity_kwh if cost_electricity_kwh > 0 else 0

            settings = [
                Setting(key="standard_price_per_load", value="210.00"),
                Setting(key="wait_and_save_price_per_load", value="150.00"),
                Setting(key="default_dispatch_method", value="inhouse"),
                Setting(key="pickup_time_minutes", value="60"),
                Setting(key="insurance_amount", value="5000"),
                Setting(key="wash_cycle_time_seconds", value="1800"),
                Setting(key="dry_cycle_time_seconds", value="7200"),
                Setting(key="fold_cycle_time_seconds", value="300"),
                Setting(key="imaging_time_seconds_per_load", value="300"),
                Setting(key="kpi_goal_turnaround_minutes", value="150"),
                Setting(key="kpi_goal_pickup_minutes", value="15"),
                Setting(key="kpi_goal_delivery_minutes", value="15"),
                Setting(key="kpi_goal_claim_minutes", value="5"),
                Setting(key="qa_time_seconds_per_load", value="300"),
                Setting(key="packaging_time_seconds_per_load", value="180"),
                Setting(key="driver_hub_delivery_qr", value="DRIVER-DELIVERS-TO-HUB"),
                Setting(key="driver_hub_pickup_qr", value="DRIVER-PICKS-UP-FROM-HUB"),
                Setting(key="washing_machine_count", value="1"),
                Setting(key="drying_machine_count", value="2"),
                Setting(key="folding_machine_count", value="1"),
                Setting(key="cost_rent_monthly", value=str(cost_base_electricity_monthly)),
                Setting(key="cost_insurance_monthly", value="566.0"),
                Setting(key="cost_base_electricity_monthly", value="500.0"),
                Setting(key="finance_safety_buffer_percent", value="10"),
                Setting(key="monthly_tracker_electricity_kwh", value="0"),
                Setting(key="monthly_budget_electricity_kwh", value=str(monthly_budget_kwh)),
                Setting(key="cost_electricity_kwh", value=str(cost_electricity_kwh)),
                Setting(key="usage_kwh_per_wash", value="1.5"),
                Setting(key="usage_kwh_per_dry", value="4.0"),
                Setting(key="usage_water_kl_per_wash", value="0.05"), # 50 liters
                Setting(key="usage_water_kl_per_stain", value="0.0005"), # 0.5 liters
                Setting(key="cost_maintenance_per_cycle", value="0.50"),
                Setting(key="usage_soap_kg_per_load", value="0.1"),
                Setting(key="usage_softener_l_per_load", value="0.05"),
                Setting(key="usage_stainremover_l_per_stain", value="0.01"),
                Setting(key="usage_bags_per_order", value="2"),
                Setting(key="cost_water_kl_tier1_rate", value="22.52"),
                Setting(key="cost_water_kl_tier1_limit", value="6"),
                Setting(key="cost_water_kl_tier2_rate", value="30.96"),
                Setting(key="cost_water_kl_tier2_limit", value="10.5"),
                Setting(key="cost_water_kl_tier3_rate", value="42.07"),
                Setting(key="cost_water_kl_tier3_limit", value="35"),
                Setting(key="cost_water_kl_tier4_rate", value="77.63"),
            ]
            session.add_all(settings)
            session.commit()
        else:
            print("Settings already exist. Skipping creation.")
        
        settings_dict = {s.key: s.value for s in session.exec(select(Setting)).all()}
        
        inventory_check = session.exec(select(InventoryItem)).first()
        if not inventory_check:
            print("No inventory items found. Creating defaults...")
            
            usage_soap_kg_per_load = float(settings_dict.get('usage_soap_kg_per_load', 0.1))
            soap_threshold = 15.0 * usage_soap_kg_per_load
            
            inventory_items = [
                InventoryItem(sku="SOAP-001", name="Washing Powder", current_stock_level=10.0, unit_of_measurement="kg", low_stock_threshold=soap_threshold, average_cost_per_unit=35.0),
                InventoryItem(sku="SOFT-001", name="Fabric Softener", current_stock_level=5.0, unit_of_measurement="liters", low_stock_threshold=1.0, average_cost_per_unit=40.0),
                InventoryItem(sku="STAIN-001", name="Stain Remover", current_stock_level=2.0, unit_of_measurement="liters", low_stock_threshold=0.5, average_cost_per_unit=75.0),
                InventoryItem(sku="BAG-001", name="Plastic Bags", current_stock_level=500, unit_of_measurement="units", low_stock_threshold=100, average_cost_per_unit=2.0),
            ]
            session.add_all(inventory_items)
            session.commit()
        else:
            print("Inventory items already exist. Skipping creation.")

        user_check = session.exec(select(User)).first()
        if not user_check:
            print("No users found. Creating default users...")
            admin_user = os.getenv("ADMIN_USER", "admin")
            admin_email = os.getenv("ADMIN_EMAIL", "admin@example.com")
            admin_pass = os.getenv("ADMIN_PASSWORD", "admin")
            
            user_admin = User(username=admin_user, email=admin_email, hashed_password=get_password_hash(admin_pass), role="admin", display_name="Admin User", is_active=True)
            user_driver = User(username="driver1", email="driver1@example.com", hashed_password=get_password_hash("password"), role="driver", display_name="Sample Driver", is_active=True)
            user_staff = User(username="staff1", email="staff1@example.com", hashed_password=get_password_hash("password"), role="staff", display_name="Hub Staff Member", is_active=True, allowed_stations="hub_intake,imaging,pretreat,washing,drying,folding,qa_station")
            session.add_all([user_admin, user_driver, user_staff])
            session.commit()
            print(f"-> Created ADMIN user: {user_admin.username} (active: {user_admin.is_active})")
            print(f"-> Created DRIVER user: {user_driver.username} (active: {user_driver.is_active})")
            print(f"-> Created STAFF user: {user_staff.username} (active: {user_staff.is_active}) with full station access.")
        else:
            print("Users already exist. Skipping creation.")

        station_check = session.exec(select(Station)).first()
        if not station_check:
            print("No stations found. Creating stations for Hub 1...")
            stations = [
                Station(hub_id=1, type="imaging", capacity=5, title="Imaging Station"), Station(hub_id=1, type="Pretreat", capacity=5, title="Pretreat Station"),
                Station(hub_id=1, type="washing", capacity=10, title="Washing Station"), Station(hub_id=1, type="drying", capacity=10, title="Drying Station"),
                Station(hub_id=1, type="folding", capacity=8, title="Folding Station"), Station(hub_id=1, type="qa", capacity=5, title="Quality Assurance"),
            ]
            session.add_all(stations)
            session.commit()
            
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

        order_check = session.exec(select(Order)).first()
        if not order_check:
            print("No orders found. Creating 3 sample orders...")
            for i, name in enumerate(["Alice Wonderland", "Bob Builder", "Charlie Chocolate"]):
                token, sla = str(uuid.uuid4()), None
                if i == 0: sla = datetime.now(timezone.utc) + timedelta(minutes=1)
                order = Order(external_id=f"ext_{token[:6]}", tracking_token=token, customer_name=name, customer_phone="123-555-0101", customer_address="123 Main St", status="Created", sla_deadline=sla)
                session.add(order)
                session.commit()
                session.refresh(order)
                bag = Bag(order_id=order.id, bag_code=f"BAG-{secrets.token_hex(4).upper()}")
                session.add(bag)
                session.commit()
                print(f"  - Created Order ID: {order.id} with status '{order.status}' and Bag Code '{bag.bag_code}'")
        else:
            print("Orders already exist. Skipping creation.")

    print("--- Database seed finished ---")

if __name__ == "__main__":
    seed_database()