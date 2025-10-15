# 🚨 Delivery Cost Implementation - Backend Changes Complete

## Summary

This document details the backend implementation for tracking delivery costs and providing pricing information to the mobile app. These changes fix the issue where delivery costs were calculated but never persisted to the database.

---

## Problem Statement

The mobile app was calculating `delivery_cost` and `pickup_cost` but:
1. **Delivery cost** was never sent to or saved by the backend
2. **Price per load** was not being returned in API responses
3. Orders showed R0 for delivery cost after app restart

---

## Changes Implemented

### 1. Database Model Updates (`app/models.py`)

#### Added New Fields to Order Model:
```python
delivery_cost: Optional[float] = Field(default=None)
delivery_distance_km: Optional[float] = Field(default=None)
```

**Line 76-77**: These fields store the cost and distance for delivering an order back to the customer.

### 2. API Endpoint Updates (`app/routes/orders.py`)

#### A. Updated DeliveryRequest Model (Lines 106-112):
```python
class DeliveryRequest(BaseModel):
    delivery_address: str
    delivery_latitude: float
    delivery_longitude: float
    phone: str
    delivery_cost: Optional[float] = None      # NEW
    distance_km: Optional[float] = None        # NEW
```

#### B. Updated OrderResponse Model (Lines 20-32):
```python
class OrderResponse(BaseModel):
    id: int
    customer_id: int
    status: str
    total_cost: float
    number_of_loads: int
    created_at: datetime
    driver_name: Optional[str] = None
    driver_id: Optional[int] = None
    processing_option: Optional[str] = None
    price_per_load: Optional[float] = None     # NEW
    pickup_cost: Optional[float] = None        # NEW
    delivery_cost: Optional[float] = None      # NEW
```

#### C. Updated `/api/orders/{order_id}/request-delivery` Endpoint (Lines 245-279):
The endpoint now:
- Accepts `delivery_cost` and `distance_km` from the mobile app
- Saves them to the Order record
- Updates delivery location fields (lat/lon, address, phone)
- Updates customer profile with new delivery details

**Key Changes:**
```python
# Update order with delivery cost and distance
if delivery_request.delivery_cost is not None:
    order.delivery_cost = delivery_request.delivery_cost
if delivery_request.distance_km is not None:
    order.delivery_distance_km = delivery_request.distance_km

# Update delivery location
order.delivery_lat = delivery_request.delivery_latitude
order.delivery_lon = delivery_request.delivery_longitude
order.customer_address = delivery_request.delivery_address
order.customer_phone = delivery_request.phone
```

#### D. Updated `/api/orders/my-orders` Endpoint (Lines 35-105):
Now calculates and returns:
- `price_per_load` based on the order's `processing_option`
  - `wait_and_save`: Uses `wait_and_save_price_per_load` setting (default: R150)
  - `standard`: Uses `standard_price_per_load` setting (default: R210)
- `pickup_cost` from the Order record
- `delivery_cost` from the Order record

**Price Calculation Logic:**
```python
# Get price_per_load based on processing_option
price_per_load = None
if order.processing_option == "wait_and_save":
    price_setting = session.get(Setting, "wait_and_save_price_per_load")
    price_per_load = float(price_setting.value) if price_setting else 150.0
else:  # standard or None defaults to standard
    price_setting = session.get(Setting, "standard_price_per_load")
    price_per_load = float(price_setting.value) if price_setting else 210.0
```

### 3. Web Dashboard Updates (`app/routes/users.py`)

#### Updated `/account` Endpoint (Lines 342-413):
The web account page now includes:
- `price_per_load` calculation (same logic as mobile API)
- `delivery_cost` and `delivery_distance_km` in enhanced order objects

This ensures consistency between mobile app and web interface.

---

## How It Works

### Booking Flow (Pickup):
1. Mobile app calculates `pickup_cost` based on distance from customer to facility
2. App sends `pickup_cost` and `distance_km` in booking request
3. Backend saves to Order: `pickup_cost`, `distance_km`

### Delivery Flow (Return to Customer):
1. Order reaches "ReadyForDelivery" status
2. Customer schedules delivery in mobile app
3. App calculates `delivery_cost` based on distance from facility to delivery address
4. App sends POST to `/api/orders/{order_id}/request-delivery` with:
   ```json
   {
     "delivery_address": "string",
     "delivery_latitude": number,
     "delivery_longitude": number,
     "phone": "string",
     "delivery_cost": number,
     "distance_km": number
   }
   ```
5. Backend saves to Order: `delivery_cost`, `delivery_distance_km`
6. Order transitions to "OutForDelivery"

### Mobile App Order Display:
1. App fetches orders from `/api/orders/my-orders`
2. Response includes:
   - `price_per_load`: Based on processing option (standard or wait_and_save)
   - `pickup_cost`: From Order record
   - `delivery_cost`: From Order record (null until delivery scheduled)
   - `number_of_loads`: Confirmed load count or basket count
3. App calculates total: `(number_of_loads × price_per_load) + pickup_cost + delivery_cost`

---

## Cost Calculation Formula (Mobile App)

The mobile app uses this formula for both pickup and delivery:
```
Base Cost: R25 for distances up to 2km
Additional: R5 per km beyond 2km
Total: ceil(25 + (max(0, distance - 2) × 5))
```

**Examples:**
- 1.5 km → R25
- 3 km → R30
- 10 km → R65
- 100 km → R515

---

## Database Migration

### Required Changes:
```sql
ALTER TABLE "order" ADD COLUMN delivery_cost FLOAT NULL;
ALTER TABLE "order" ADD COLUMN delivery_distance_km FLOAT NULL;
```

**Note:** Since the Order model uses SQLModel with optional fields, the database should be updated automatically on next startup. However, if using a production database with strict migrations, add the above SQL to your migration script.

---

## Testing Checklist

- [x] Order model accepts new fields
- [x] DeliveryRequest accepts delivery_cost and distance_km
- [x] Endpoint saves delivery cost to database
- [x] OrderResponse includes price_per_load, pickup_cost, delivery_cost
- [x] Price per load calculated correctly based on processing_option
- [x] Web dashboard includes new fields
- [ ] End-to-end test: Create order → Process → Schedule delivery → Verify costs persist
- [ ] Test with wait_and_save processing option
- [ ] Test with standard processing option
- [ ] Verify costs display correctly in mobile app after restart

---

## API Examples

### Request Delivery with Cost:
```bash
POST /api/orders/54/request-delivery
Content-Type: application/json

{
  "delivery_address": "123 Customer St, City",
  "delivery_latitude": -26.1234,
  "delivery_longitude": 28.5678,
  "phone": "+27123456789",
  "delivery_cost": 8667.0,
  "distance_km": 1735.0
}
```

### Get Orders Response:
```json
{
  "id": 54,
  "customer_id": 1,
  "status": "ReadyForDelivery",
  "total_cost": 0.0,
  "number_of_loads": 1,
  "created_at": "2025-10-15T10:30:00Z",
  "driver_name": null,
  "driver_id": null,
  "processing_option": "standard",
  "price_per_load": 210.0,
  "pickup_cost": 8667.0,
  "delivery_cost": null
}
```

After scheduling delivery:
```json
{
  "id": 54,
  "customer_id": 1,
  "status": "OutForDelivery",
  "total_cost": 210.0,
  "number_of_loads": 1,
  "created_at": "2025-10-15T10:30:00Z",
  "driver_name": "John Doe",
  "driver_id": 5,
  "processing_option": "standard",
  "price_per_load": 210.0,
  "pickup_cost": 8667.0,
  "delivery_cost": 8667.0
}
```

---

## Configuration

### Settings Used:
- `standard_price_per_load`: Default R210.00 per load
- `wait_and_save_price_per_load`: Default R150.00 per load

These can be modified in the admin settings panel.

---

## Answers to Original Questions

### 1. Are these timestamp fields being set correctly?

**YES** ✅ All timestamp fields are set automatically by the state machine:

- `picked_up_at`: Set when order transitions to "PickedUp" status
- `ready_for_delivery_at`: Set when order transitions to "ReadyForDelivery" status
- `delivered_at`: Set when order transitions to "Delivered" status
- `created_at`: Set automatically when order is created

**Location:** `app/services/state_machine.py` lines 28-40

### 2. For completed orders in history:

**Which timestamp indicates order completion?**
- **`delivered_at`** indicates when the order was delivered to the customer
- **`closed_at`** indicates when the order was fully closed (optional final state)

**Are all pricing fields being populated?**
- **`pickup_cost`**: ✅ Now populated during booking
- **`delivery_cost`**: ✅ Now populated when delivery is scheduled
- **`price_per_load`**: ✅ Now calculated and returned based on `processing_option`

---

## Next Steps

1. ✅ Backend changes complete
2. ⏳ Deploy backend changes
3. ⏳ Test mobile app with new backend
4. ⏳ Verify costs persist after app restart
5. ⏳ Monitor for any issues

---

## Support

If you encounter any issues with this implementation:
1. Check the logs for any database migration errors
2. Verify the Setting table has both `standard_price_per_load` and `wait_and_save_price_per_load` entries
3. Test the `/api/orders/my-orders` endpoint directly to verify response format
4. Check that the mobile app is sending `delivery_cost` in the request body

---

**Implementation Date:** October 15, 2025
**Status:** ✅ Complete - Ready for Testing

