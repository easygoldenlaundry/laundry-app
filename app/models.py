# app/models.py
from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import TEXT, Column

# --- This new function ensures all default timestamps are timezone-aware. ---
def now_utc():
    return datetime.now(timezone.utc)

class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str

class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    external_id: str
    tracking_token: str = Field(unique=True)
    customer_name: str
    customer_phone: str
    customer_address: str
    hub_id: int = Field(default=1)
    status: str = Field(default="Created")
    total_items: int = Field(default=0)
    sla_deadline: Optional[datetime] = None
    assigned_driver_id: Optional[int] = Field(default=None, foreign_key="driver.id")
    pickup_pin: Optional[str] = None
    delivery_pin: Optional[str] = None
    basket_count: Optional[int] = Field(default=0)
    notes_for_driver: Optional[str] = Field(default=None, sa_column=Column(TEXT))
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")

    # --- Fields for KPI Tracking ---
    picked_up_at: Optional[datetime] = Field(default=None)
    at_hub_at: Optional[datetime] = Field(default=None)
    imaging_started_at: Optional[datetime] = Field(default=None)
    imaging_completed_at: Optional[datetime] = Field(default=None)
    processing_started_at: Optional[datetime] = Field(default=None) 
    qa_started_at: Optional[datetime] = Field(default=None) 
    ready_for_delivery_at: Optional[datetime] = Field(default=None)
    out_for_delivery_at: Optional[datetime] = Field(default=None)
    delivered_at: Optional[datetime] = Field(default=None)
    closed_at: Optional[datetime] = Field(default=None)
    imaged_items_count: int = Field(default=0)
    
    # --- [FIX] Add relationships for events and claims ---
    events: List["Event"] = Relationship(back_populates="order")
    claims: List["Claim"] = Relationship(back_populates="order")
    baskets: List["Basket"] = Relationship(back_populates="order")
    customer: Optional["Customer"] = Relationship(back_populates="orders")

class Basket(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    basket_index: int
    status: str = Field(default="Pretreat")
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    soaking_started_at: Optional[datetime] = None

    order: Optional["Order"] = Relationship(back_populates="baskets")

class Bag(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    bag_code: str = Field(unique=True)
    order_id: int = Field(foreign_key="order.id")
    weight_kg: float = Field(default=0)
    sealed: bool = Field(default=False)
    scanned_at: Optional[datetime] = None

class Item(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    bag_id: Optional[int] = Field(default=None, foreign_key="bag.id")
    name: str
    imaged: bool = Field(default=False)
    stain_flags: Optional[str] = Field(default=None, sa_column=Column(TEXT))
    value_band: Optional[str] = None

class User(SQLModel, table=True):
    """Represents an operator, driver, or admin with login credentials."""
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True)
    email: str = Field(unique=True)
    hashed_password: str
    role: str # 'admin', 'driver', 'staff', 'customer'
    display_name: str
    is_active: bool = Field(default=False)
    created_at: datetime = Field(default_factory=now_utc)
    allowed_stations: Optional[str] = Field(default=None)


class Customer(SQLModel, table=True):
    """Represents a customer, linked to an auth user and storing their details."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    full_name: str
    phone_number: str
    address: str
    
    orders: List["Order"] = Relationship(back_populates="customer")

class Driver(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    status: str = Field(default="idle")
    last_location: Optional[str] = None
    last_seen: Optional[datetime] = None

class Station(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    hub_id: int
    type: str
    capacity: int
    title: str
    machines: List["Machine"] = Relationship(back_populates="station")

class Machine(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    station_id: int = Field(foreign_key="station.id")
    type: str
    cycle_time_seconds: int
    state: str = Field(default="idle")
    last_heartbeat: Optional[datetime] = None
    current_basket_id: Optional[int] = Field(default=None, foreign_key="basket.id")
    cycle_started_at: Optional[datetime] = Field(default=None)

    station: Optional["Station"] = Relationship(back_populates="machines")

class Event(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: Optional[int] = Field(default=None, foreign_key="order.id")
    from_status: Optional[str] = None
    to_status: str
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    timestamp: datetime = Field(default_factory=now_utc)
    meta: Optional[str] = Field(default=None, sa_column=Column(TEXT))
    
    # --- [FIX] Add back-relationship to Order ---
    order: Optional["Order"] = Relationship(back_populates="events")

class Image(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    bag_id: Optional[int] = Field(default=None, foreign_key="bag.id")
    item_id: Optional[int] = Field(default=None, foreign_key="item.id")
    path: str
    image_type: str = Field(default="generic")
    uploaded_by: Optional[int] = Field(default=None, foreign_key="user.id")
    is_stain: bool = Field(default=False)
    qa_status: Optional[str] = Field(default='pending') 
    qa_notes: Optional[str] = Field(default=None, sa_column=Column(TEXT))
    timestamp: datetime = Field(default_factory=now_utc)

class Claim(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    claim_type: str
    status: str
    amount: Optional[float] = None
    created_at: datetime = Field(default_factory=now_utc)
    resolved_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, sa_column=Column(TEXT))

    order: Optional["Order"] = Relationship(back_populates="claims")