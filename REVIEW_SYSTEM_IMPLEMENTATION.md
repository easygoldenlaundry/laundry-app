# 🌟 Rating & Review System Implementation

## Overview
Implemented a complete customer review system that allows users to rate their laundry service experience after order completion.

---

## What Was Added

### 1. Database Model (`app/models.py`)

#### New `Review` Table:
```python
class Review(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", unique=True)
    customer_id: int = Field(foreign_key="customer.id")
    pickup_delivery_rating: int = Field(ge=1, le=5)  # 1-5 stars
    laundry_quality_rating: int = Field(ge=1, le=5)  # 1-5 stars
    feedback_text: Optional[str] = Field(default=None, max_length=500)
    created_at: datetime
    updated_at: datetime
```

**Key Features:**
- ✅ One review per order (unique constraint on order_id)
- ✅ Two separate ratings: pickup/delivery service & laundry quality
- ✅ Optional feedback text (up to 500 characters)
- ✅ Relationships to Order and Customer models

#### Updated Relationships:
- `Order.review` → Optional single review
- `Customer.reviews` → List of all customer reviews

---

### 2. API Endpoint (`app/routes/orders.py`)

#### **POST `/api/orders/{orderId}/submit-review`**

**Description:** Submit customer ratings and feedback for a completed order

**Request Body:**
```json
{
  "pickup_delivery_rating": 5,
  "laundry_quality_rating": 4,
  "feedback_text": "Great service, but could improve packaging"
}
```

**Validation Rules:**
- ✅ `pickup_delivery_rating`: Integer 1-5 (required)
- ✅ `laundry_quality_rating`: Integer 1-5 (required)
- ✅ `feedback_text`: String max 500 chars (optional)
- ✅ Order must be "Delivered" or "Closed" status
- ✅ User must own the order
- ✅ One review per order (prevents duplicates)

**Response (Success - 200 OK):**
```json
{
  "message": "Thank you for your feedback!",
  "review_id": 123,
  "order_id": 54
}
```

**Error Responses:**
- `400 Bad Request` - Order not completed yet or invalid ratings
- `404 Not Found` - Order doesn't exist or doesn't belong to user
- `409 Conflict` - Review already submitted for this order
- `401 Unauthorized` - User not authenticated

---

### 3. Updated Order Responses

The `/api/orders/my-orders` endpoint now includes review data:

```json
{
  "id": 54,
  "status": "Delivered",
  "total_cost": 210.0,
  "number_of_loads": 1,
  "has_review": true,
  "pickup_delivery_rating": 5,
  "laundry_quality_rating": 4,
  "feedback_text": "Great service!",
  "reviewed_at": "2025-10-15T10:30:00Z",
  ...
}
```

**New Fields in OrderResponse:**
- `has_review` (bool) - Whether order has been reviewed
- `pickup_delivery_rating` (int | null) - 1-5 stars
- `laundry_quality_rating` (int | null) - 1-5 stars
- `feedback_text` (string | null) - Customer feedback
- `reviewed_at` (datetime | null) - When review was submitted

This allows the mobile app to:
- ✅ Check if an order has already been reviewed
- ✅ Display existing ratings if user returns to the screen
- ✅ Show review status in order history
- ✅ Prevent duplicate review submissions

---

## Implementation Details

### Endpoint Logic Flow:

1. **Authentication Check**
   - Verify user is authenticated
   - Get customer profile for user

2. **Order Validation**
   - Verify order exists
   - Verify order belongs to authenticated user
   - Check order status is "Delivered" or "Closed"

3. **Duplicate Prevention**
   - Check if review already exists for this order
   - Return 409 Conflict if duplicate

4. **Create Review**
   - Validate ratings (1-5)
   - Validate feedback length (max 500 chars)
   - Save review to database
   - Return success message

### Database Schema:

```sql
CREATE TABLE review (
    id SERIAL PRIMARY KEY,
    order_id INTEGER UNIQUE REFERENCES "order"(id),
    customer_id INTEGER REFERENCES customer(id),
    pickup_delivery_rating INTEGER NOT NULL CHECK (pickup_delivery_rating >= 1 AND pickup_delivery_rating <= 5),
    laundry_quality_rating INTEGER NOT NULL CHECK (laundry_quality_rating >= 1 AND laundry_quality_rating <= 5),
    feedback_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_review_order_id ON review(order_id);
CREATE INDEX idx_review_customer_id ON review(customer_id);
```

---

## Testing

### Manual Testing Steps:

1. **Create and complete an order:**
   ```bash
   # Order should be in "Delivered" or "Closed" status
   ```

2. **Submit a review:**
   ```bash
   POST /api/orders/54/submit-review
   Authorization: Bearer {token}
   Content-Type: application/json
   
   {
     "pickup_delivery_rating": 5,
     "laundry_quality_rating": 4,
     "feedback_text": "Excellent service!"
   }
   ```

3. **Verify response:**
   ```json
   {
     "message": "Thank you for your feedback!",
     "review_id": 1,
     "order_id": 54
   }
   ```

4. **Try to submit again (should fail):**
   ```bash
   # Should return 409 Conflict
   ```

5. **Check order list:**
   ```bash
   GET /api/orders/my-orders
   # Should show has_review: true and rating data
   ```

### Test Cases:

- ✅ Submit valid review → Success
- ✅ Submit review for incomplete order → 400 Error
- ✅ Submit duplicate review → 409 Error
- ✅ Submit review for non-existent order → 404 Error
- ✅ Submit review for other user's order → 404 Error
- ✅ Submit with invalid ratings (0, 6, etc.) → 422 Validation Error
- ✅ Submit with too long feedback (>500 chars) → 422 Validation Error
- ✅ Submit without authentication → 401 Error

---

## Mobile App Integration

The mobile app will:

1. **Display Rating Screen** (after delivery)
   - Show when order status is "Delivered"
   - Check `has_review` field to prevent showing again

2. **Collect Ratings**
   - Pickup/Delivery Service: 1-5 stars
   - Laundry Quality: 1-5 stars
   - Optional feedback textarea

3. **Submit Review**
   ```kotlin
   POST /api/orders/{orderId}/submit-review
   {
     "pickup_delivery_rating": 5,
     "laundry_quality_rating": 4,
     "feedback_text": "Great service!"
   }
   ```

4. **Handle Response**
   - Show success message
   - Navigate to home screen
   - Update local order data to reflect review submitted

5. **Display Status**
   - Show "Already Reviewed" if `has_review = true`
   - Display existing ratings in order history

---

## Analytics Opportunities

With this review data, you can track:

### Overall Metrics:
- Average pickup/delivery rating
- Average laundry quality rating
- Percentage of orders reviewed
- Review submission rate over time

### Segmented Analytics:
- Driver performance (via order → driver relationship)
- Processing option satisfaction (standard vs wait_and_save)
- Regional performance (by customer location)
- Temporal patterns (time of day, day of week)

### Feedback Analysis:
- Common keywords in feedback
- Sentiment analysis
- Issue categorization
- Service improvement themes

### Example Queries:

```python
# Average ratings
avg_delivery = db.query(func.avg(Review.pickup_delivery_rating)).scalar()
avg_quality = db.query(func.avg(Review.laundry_quality_rating)).scalar()

# Driver performance
driver_reviews = db.query(
    Driver.id,
    func.avg(Review.pickup_delivery_rating).label('avg_rating'),
    func.count(Review.id).label('total_reviews')
).join(Order).join(Review).group_by(Driver.id)

# Recent feedback
recent_feedback = db.query(Review).filter(
    Review.feedback_text.isnot(None),
    Review.created_at >= datetime.now() - timedelta(days=7)
).order_by(Review.created_at.desc()).all()

# Low ratings (need attention)
low_ratings = db.query(Review, Order).join(Order).filter(
    or_(
        Review.pickup_delivery_rating <= 2,
        Review.laundry_quality_rating <= 2
    )
).all()
```

---

## Future Enhancements

Potential features to add:

1. **Review Response**
   - Allow admin to respond to customer reviews
   - Display admin response in mobile app

2. **Review Moderation**
   - Flag inappropriate feedback
   - Admin review dashboard

3. **Review Incentives**
   - Discount/reward for submitting reviews
   - Badge system for active reviewers

4. **Public Reviews**
   - Display reviews on website
   - Aggregate ratings display
   - Testimonials section

5. **Detailed Categories**
   - Rating for specific aspects (speed, care, packaging, etc.)
   - Multi-dimensional feedback

6. **Review Reminders**
   - Push notification to review after delivery
   - Email reminder if not reviewed after 24h

---

## Database Migration

The Review table will be created automatically on server restart.

To manually create the table:

```sql
CREATE TABLE review (
    id SERIAL PRIMARY KEY,
    order_id INTEGER UNIQUE REFERENCES "order"(id) ON DELETE CASCADE,
    customer_id INTEGER REFERENCES customer(id) ON DELETE CASCADE,
    pickup_delivery_rating INTEGER NOT NULL CHECK (pickup_delivery_rating BETWEEN 1 AND 5),
    laundry_quality_rating INTEGER NOT NULL CHECK (laundry_quality_rating BETWEEN 1 AND 5),
    feedback_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_review_order_id ON review(order_id);
CREATE INDEX idx_review_customer_id ON review(customer_id);
CREATE INDEX idx_review_created_at ON review(created_at DESC);
```

---

## Summary

### ✅ Completed:
- Review database model with proper relationships
- POST endpoint to submit reviews
- Validation for ratings, order status, and ownership
- Duplicate review prevention
- Review data in order responses
- Comprehensive error handling

### 📱 Mobile App Ready:
The backend is fully prepared to receive and store customer reviews. The mobile app can now:
- Submit reviews after order completion
- Check if orders have been reviewed
- Display existing review data
- Handle all error scenarios

### 🚀 Ready to Deploy:
- All code tested and compiling
- No linting errors
- Backward compatible (new optional fields)
- Auto-migration on server restart

---

**Implementation Date:** October 15, 2025  
**Status:** ✅ Complete - Ready for Production

**Files Modified:**
- `app/models.py` - Added Review model
- `app/routes/orders.py` - Added review endpoint and updated responses

**New Endpoint:**
- `POST /api/orders/{orderId}/submit-review`

