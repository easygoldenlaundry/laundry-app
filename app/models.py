# app/models.py
from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import TEXT, Column

def now_utc():
    return datetime.now(timezone.utc)

# --- NEW MODEL ---
class InventoryItem(SQLModel, table=True):
    sku: str = Field(primary_key=True)
    name: str
    current_stock_level: float = Field(default=0.0)
    unit_of_measurement: str  # 'kg', 'liters', 'units'
    low_stock_threshold: float = Field(default=0.0)
    average_cost_per_unit: float = Field(default=0.0)

# --- NEW MODEL ---
class Withdrawal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    amount: float
    withdrawal_type: str  # 'cost_reimbursement', 'profit_draw', 'capital_expenditure', 'fixed_cost'
    description: str = Field(sa_column=Column(TEXT))
    timestamp: datetime = Field(default_factory=now_utc)
    inventory_item_sku: Optional[str] = Field(default=None, foreign_key="inventoryitem.sku")
    quantity_purchased: Optional[float] = None

class FinanceEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: Optional[int] = Field(default=None, foreign_key="order.id")
    entry_type: str  # 'revenue', 'variable_cost', 'fixed_cost_accrual'
    amount: float
    description: str = Field(sa_column=Column(TEXT))
    timestamp: datetime = Field(default_factory=now_utc)
    
    order: Optional["Order"] = Relationship(back_populates="finance_entries")

class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    sender_role: str  # 'admin' or 'customer'
    content: str = Field(sa_column=Column(TEXT))
    timestamp: datetime = Field(default_factory=now_utc)
    is_read: bool = Field(default=False)
    
    order: Optional["Order"] = Relationship(back_populates="messages")

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
    confirmed_load_count: Optional[int] = Field(default=None)
    dispatch_method: Optional[str] = Field(default="inhouse")
    distance_km: Optional[float] = Field(default=None)
    pickup_cost: Optional[float] = Field(default=None)
    delivery_cost: Optional[float] = Field(default=None)
    delivery_distance_km: Optional[float] = Field(default=None)
    processing_option: Optional[str] = Field(default="standard")  # "standard" or "wait_and_save"

    # --- PAYMENT FIELDS ---
    payment_status: str = Field(default="pending")  # "pending", "paid", "failed"
    payment_method: Optional[str] = Field(default=None)  # "card", "bank_transfer", "cash", etc.
    paystack_reference: Optional[str] = Field(default=None)  # Paystack payment reference

    # --- NEW FIELDS FOR DRIVER TRACKING ---
    pickup_lat: Optional[float] = None
    pickup_lon: Optional[float] = None
    delivery_lat: Optional[float] = None
    delivery_lon: Optional[float] = None
    initial_driver_lat: Optional[float] = None
    initial_driver_lon: Optional[float] = None


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
    
    events: List["Event"] = Relationship(back_populates="order")
    claims: List["Claim"] = Relationship(back_populates="order")
    baskets: List["Basket"] = Relationship(back_populates="order")
    customer: Optional["Customer"] = Relationship(back_populates="orders")
    bags: List["Bag"] = Relationship(back_populates="order")
    images: List["Image"] = Relationship(back_populates="order")
    messages: List["Message"] = Relationship(back_populates="order")
    finance_entries: List["FinanceEntry"] = Relationship(back_populates="order")
    review: Optional["Review"] = Relationship(back_populates="order")

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
    order: Optional["Order"] = Relationship(back_populates="bags")

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
    # --- NEW FIELDS FOR MOBILE APP ---
    whatsapp_number: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # --- NEW FIELDS FOR STAYSOFT PREFERENCE AND NOTES ---
    staysoft_preference: Optional[str] = None  # "NO_STAYSOFT", "LAVENDER", "SPRING_FRESH", "JASMINE_CASHMERE"
    additional_notes: Optional[str] = Field(default=None, sa_column=Column(TEXT))
    
    orders: List["Order"] = Relationship(back_populates="customer")
    reviews: List["Review"] = Relationship(back_populates="customer")

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
    order: Optional["Order"] = Relationship(back_populates="images")

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

class Review(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", unique=True)
    customer_id: int = Field(foreign_key="customer.id")
    pickup_delivery_rating: int = Field(ge=1, le=5)  # 1-5 stars
    laundry_quality_rating: int = Field(ge=1, le=5)  # 1-5 stars
    feedback_text: Optional[str] = Field(default=None, max_length=500, sa_column=Column(TEXT))
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)
    
    order: Optional["Order"] = Relationship(back_populates="review")
    customer: Optional["Customer"] = Relationship(back_populates="reviews")