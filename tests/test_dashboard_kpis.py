# tests/test_dashboard_kpis.py
import pytest
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, SQLModel, create_engine
import uuid
import json 

from app.models import Order, Claim, Station, Machine, Event, Basket, Image, Customer
from app.queries import dashboard_queries

engine = create_engine("sqlite:///:memory:")

def setup_database():
    SQLModel.metadata.create_all(engine)

def seed_test_data(session: Session):
    now = datetime.now(timezone.utc)
    
    stations = [
        Station(id=1, hub_id=1, type="imaging", capacity=5, title="Imaging Station"),
        Station(id=2, hub_id=1, type="pretreat", capacity=5, title="Pretreat Station"),
        Station(id=3, hub_id=1, type="washing", capacity=5, title="Washing Station"),
        Station(id=4, hub_id=1, type="drying", capacity=5, title="Drying Station"),
        Station(id=5, hub_id=1, type="folding", capacity=5, title="Folding Station"),
        Station(id=6, hub_id=1, type="qa", capacity=5, title="QA Station")
    ]
    session.add_all(stations)
    session.commit()

    machines = [Machine(id=i, station_id=3, type="washer", cycle_time_seconds=1800, state="idle" if i < 3 else "running") for i in range(1, 4)]
    session.add_all(machines)

    customer = Customer(id=1, user_id=1, full_name="Test Customer 1", phone_number="123", address="123")
    session.add(customer)

    orders_data = [
        {"id": 1, "status": "Delivered", "created_at": now - timedelta(hours=3), "picked_up_at": now - timedelta(hours=2, minutes=50), "delivered_at": now - timedelta(hours=1), "out_for_delivery_at": now - timedelta(hours=1, minutes=10), "imaging_started_at": now - timedelta(hours=2, minutes=35), "imaging_completed_at": now - timedelta(hours=2, minutes=30), "processing_started_at": now - timedelta(hours=2, minutes=30), "qa_started_at": now - timedelta(hours=1, minutes=20), "ready_for_delivery_at": now - timedelta(hours=1, minutes=15), "total_items": 5, "imaged_items_count": 5},
        {"id": 2, "status": "Delivered", "created_at": now - timedelta(hours=5), "picked_up_at": now - timedelta(hours=4, minutes=55), "delivered_at": now - timedelta(hours=1), "out_for_delivery_at": now - timedelta(hours=1, minutes=5), "imaging_started_at": now - timedelta(hours=4, minutes=45), "imaging_completed_at": now - timedelta(hours=4, minutes=30), "processing_started_at": now - timedelta(hours=4, minutes=30), "qa_started_at": now - timedelta(hours=1, minutes=20), "ready_for_delivery_at": now - timedelta(hours=1, minutes=15), "total_items": 10, "imaged_items_count": 10},
        {"id": 3, "status": "Delivered", "created_at": now - timedelta(hours=2), "picked_up_at": now - timedelta(hours=1, minutes=30), "delivered_at": now - timedelta(hours=1), "out_for_delivery_at": now - timedelta(hours=1, minutes=12), "imaging_started_at": now - timedelta(hours=1, minutes=55), "imaging_completed_at": now - timedelta(hours=1, minutes=45), "processing_started_at": now - timedelta(hours=1, minutes=45), "qa_started_at": now - timedelta(hours=1, minutes=20), "ready_for_delivery_at": now - timedelta(hours=1, minutes=15), "total_items": 8, "imaged_items_count": 7},
        {"id": 4, "status": "Processing", "created_at": now - timedelta(hours=2), "picked_up_at": now - timedelta(hours=1, minutes=55), "sla_deadline": now + timedelta(minutes=20), "imaging_started_at": now - timedelta(hours=1, minutes=40), "imaging_completed_at": now - timedelta(hours=1, minutes=35), "processing_started_at": now - timedelta(hours=1, minutes=30), "total_items": 6, "imaged_items_count": 6, "basket_count": 2},
        {"id": 5, "status": "Created", "created_at": now - timedelta(minutes=10), "total_items": 3},
        {"id": 6, "status": "Delivered", "created_at": now - timedelta(hours=1), "picked_up_at": now - timedelta(minutes=50), "delivered_at": now - timedelta(minutes=10), "out_for_delivery_at": now - timedelta(minutes=30), "imaging_started_at": now - timedelta(minutes=45), "imaging_completed_at": now - timedelta(minutes=40), "processing_started_at": now - timedelta(minutes=40), "qa_started_at": now - timedelta(minutes=38), "ready_for_delivery_at": now - timedelta(minutes=35), "total_items": 12, "imaged_items_count": 11},
        {"id": 7, "status": "Processing", "created_at": now - timedelta(hours=3), "picked_up_at": now - timedelta(hours=2, minutes=50), "sla_deadline": now - timedelta(minutes=10), "imaging_started_at": now - timedelta(hours=2, minutes=10), "imaging_completed_at": now - timedelta(hours=2, minutes=5), "processing_started_at": now - timedelta(hours=2, minutes=5), "total_items": 7, "imaged_items_count": 7, "basket_count": 1},
        {"id": 8, "status": "Delivered", "created_at": now - timedelta(hours=30), "picked_up_at": now - timedelta(hours=29), "total_items": 1, "imaged_items_count": 1},
        {"id": 9, "status": "Processing", "created_at": now - timedelta(hours=4), "picked_up_at": now - timedelta(hours=3, minutes=50), "qa_started_at": now - timedelta(hours=1, minutes=10), "imaging_completed_at": now - timedelta(hours=3, minutes=25), "total_items": 4, "imaged_items_count": 4, "basket_count": 1},
    ]
    for data in orders_data:
        session.add(Order(**data, external_id=str(uuid.uuid4()), tracking_token=str(uuid.uuid4()), customer_name="Test", customer_phone="123", customer_address="123"))
    session.commit()

    baskets = [Basket(id=401, order_id=4, basket_index=1, status="Washing"), Basket(id=402, order_id=4, basket_index=2, status="Pretreat"), Basket(id=701, order_id=7, basket_index=1, status="Drying"), Basket(id=901, order_id=9, basket_index=1, status="Pretreat")]
    session.add_all(baskets)
    
    events = [
        Event(order_id=1, to_status="Basket-1-Started-washing", timestamp=now - timedelta(hours=2, minutes=15), meta='{"basket_id": 1}'),
        Event(order_id=1, to_status="Basket-1-Finished-washing", timestamp=now - timedelta(hours=1, minutes=45), meta='{"basket_id": 1}'),
        Event(order_id=1, to_status="QA", timestamp=now - timedelta(hours=1, minutes=20)),
        Event(order_id=1, to_status="ReadyForDelivery", timestamp=now - timedelta(hours=1, minutes=15)),
        Event(order_id=9, to_status="QA", timestamp=now - timedelta(hours=1, minutes=10)),
        Event(order_id=9, to_status="Processing", timestamp=now - timedelta(hours=1, minutes=5), meta='{"qa_failed_by": 1}'),
    ]
    session.add_all(events)
    session.add(Image(order_id=1, is_stain=True, path="test"))
    session.add(Claim(order_id=1, status='open', claim_type='delay', created_at=now - timedelta(hours=1), amount=50.0))
    session.commit()

@pytest.fixture(name="session")
def session_fixture():
    setup_database()
    with Session(engine) as session:
        seed_test_data(session)
        yield session
    SQLModel.metadata.drop_all(engine)

def test_turnaround_kpi(session: Session):
    result = dashboard_queries.get_turnaround_kpi(session, window_hours=24)
    assert result['total_completed'] == 4
    assert result['percentage_on_time'] == pytest.approx(75.0, 0.1)
    assert result['p50_minutes'] == pytest.approx(75.0)
    assert result['p90_minutes'] == pytest.approx(197.5)
    assert result['p95_minutes'] == pytest.approx(216.25)

def test_pickup_kpi(session: Session):
    result = dashboard_queries.get_pickup_kpi(session, window_hours=24)
    assert result['total_pickups'] == 7
    assert result['percentage_on_time'] == pytest.approx(71.4, 0.1)
    assert result['median_pickup_time'] == 10.0

def test_delivery_kpi(session: Session):
    result = dashboard_queries.get_delivery_kpi(session, window_hours=24)
    assert result['total_deliveries'] == 4
    assert result['percentage_on_time'] == pytest.approx(75.0, 0.1)
    assert result['avg_delivery_time'] == pytest.approx(11.75, 0.1)

def test_image_coverage_kpi(session: Session):
    result = dashboard_queries.get_image_coverage_kpi(session, window_hours=24)
    assert result['total_items'] == 52
    assert result['imaged_items'] == 50
    assert result['coverage_percent'] == pytest.approx(96.15, 0.1)

def test_active_inflight_orders(session: Session):
    result = dashboard_queries.get_active_inflight_orders(session)
    assert len(result) == 4

def test_claims_summary(session: Session):
    result = dashboard_queries.get_claims_summary(session, window_hours=24)
    assert result['count_today'] == 1
    assert result['open_count'] == 1
    assert result['total_compensation'] == 50.0

def test_station_metrics(session: Session):
    wash_metrics = dashboard_queries.get_station_metrics(session, "washing", window_hours=24)
    assert wash_metrics['queue_length'] == 1
    assert wash_metrics['utilization_pct'] == pytest.approx(33.3, 0.1)
    assert wash_metrics['avg_time'] == pytest.approx(30.0)
    assert wash_metrics['throughput_h'] == pytest.approx(1 / 24, 0.1)

def test_aggregated_stats(session: Session):
    result = dashboard_queries.get_aggregated_stats(session, timeframe_days=1)
    assert result['total_orders_created'] == 8
    assert result['total_orders_completed'] == 4
    assert result['avg_turnaround_minutes'] == pytest.approx(103.8, 0.1)
    assert result['avg_pickup_minutes'] == pytest.approx(15.7, 0.1)
    assert result['avg_imaging_time'] == pytest.approx(11.2, 0.1)
    assert result['percent_qa_passed'] == pytest.approx(50.0)
    assert result['percent_qa_failed'] == pytest.approx(50.0)