# tests/test_imaging_upload.py
import os
import pytest
from httpx import AsyncClient
from sqlmodel import Session, select

from app.models import Order, Bag, Image, Item

# Mark all tests in this file as async
pytestmark = pytest.mark.asyncio

async def test_upload_item_image(client: AsyncClient, session: Session, tmp_path, monkeypatch):
    """
    GIVEN an order in the 'Imaging' state
    WHEN an image is uploaded for an item
    THEN an Item and Image record are created in the DB
    AND the image file is saved to the configured data directory
    """
    # GIVEN
    # Use monkeypatch to redirect DATA_ROOT to a temporary directory for this test
    monkeypatch.setattr("app.config.DATA_ROOT", str(tmp_path))
    monkeypatch.setattr("app.routes.orders.DATA_ROOT", str(tmp_path)) # Ensure patched in routes too

    order = Order(
        external_id="img_order_1", tracking_token="img_token_1",
        customer_name="Test Customer", customer_phone="555-IMG",
        customer_address="123 Camera St", status="Imaging"
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    
    bag = Bag(order_id=order.id, bag_code=f"BAG-IMG{order.id}")
    session.add(bag)
    session.commit()
    session.refresh(bag)
    
    # Define file content and form data
    fake_image_bytes = b"this is a fake jpeg"
    files = {"proof_photo": ("test_image.jpg", fake_image_bytes, "image/jpeg")}
    form_data = {
        "bag_id": bag.id,
        "item_index": 1,
        "user_id": 1,
        "is_stain": "false"
    }

    # WHEN
    response = await client.post(
        f"/api/orders/{order.id}/upload-image",
        data=form_data,
        files=files
    )
    
    # THEN
    assert response.status_code == 200
    response_data = response.json()
    assert "image_id" in response_data
    assert "item_id" in response_data

    # Check database records
    db_image = session.get(Image, response_data["image_id"])
    assert db_image is not None
    assert db_image.order_id == order.id
    assert db_image.item_id == response_data["item_id"]
    
    db_item = session.get(Item, response_data["item_id"])
    assert db_item is not None
    assert db_item.order_id == order.id
    assert db_item.name == "Item #1"

    # Check that the file was written to disk in the temp path
    expected_file_path = tmp_path / db_image.path.replace("data/", "")
    assert os.path.exists(expected_file_path)
    with open(expected_file_path, "rb") as f:
        content = f.read()
        assert content == fake_image_bytes