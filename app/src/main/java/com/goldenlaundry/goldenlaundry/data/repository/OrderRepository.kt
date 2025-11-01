package com.goldenlaundry.goldenlaundry.data.repository

import com.goldenlaundry.goldenlaundry.data.local.PreferencesManager
import com.goldenlaundry.goldenlaundry.data.model.*
import com.goldenlaundry.goldenlaundry.data.remote.ApiService
import com.goldenlaundry.goldenlaundry.data.remote.PaymentResponse

class OrderRepository(
    private val apiService: ApiService,
    private val preferencesManager: PreferencesManager
) {
    
    suspend fun createBooking(request: BookingRequest): Result<Order> {
        return try {
            val response = apiService.createBooking(
                pickupAddress = request.pickupAddress,
                pickupLatitude = request.pickupLatitude,
                pickupLongitude = request.pickupLongitude,
                phone = request.phone,
                processingOption = request.processingOption,
                termsAccepted = request.termsAccepted,
                distanceKm = request.distanceKm,
                pickupCost = request.pickupCost
            )
            if (response.isSuccessful && response.body() != null) {
                val bookingResponse = response.body()!!
                val order = bookingResponse.order
                preferencesManager.saveActiveOrderId(order.id.toString())
                Result.success(order)
            } else {
                Result.failure(Exception(response.message() ?: "Booking failed"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    suspend fun getMyOrders(): Result<List<Order>> {
        return try {
            val response = apiService.getMyOrders()
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception(response.message() ?: "Failed to get orders"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    suspend fun getOrder(orderId: String): Result<Order> {
        return try {
            android.util.Log.d("OrderRepository", "🔍 Fetching order $orderId from API")
            val response = apiService.getOrder(orderId)
            android.util.Log.d("OrderRepository", "🔍 API Response: isSuccessful=${response.isSuccessful}, code=${response.code()}")
            if (response.isSuccessful && response.body() != null) {
                val orderWithDriver = response.body()!!
                android.util.Log.d("OrderRepository", "🔍 Order data: ${orderWithDriver.order}")
                android.util.Log.d("OrderRepository", "🔍 Driver data: ${orderWithDriver.driver}")
                android.util.Log.d("OrderRepository", "🔍 Order status: ${orderWithDriver.order.status}")
                android.util.Log.d("OrderRepository", "🔍 Driver name: ${orderWithDriver.order.driverName}")
                android.util.Log.d("OrderRepository", "🔍 Driver ID: ${orderWithDriver.order.driverId}")
                
                // Merge driver information into the order
                val order = orderWithDriver.order
                val driver = orderWithDriver.driver
                
                val updatedOrder = if (driver != null) {
                    order.copy(
                        driverName = driver.displayName,
                        driverId = driver.id.toString()
                    )
                } else {
                    order
                }
                
                android.util.Log.d("OrderRepository", "🔍 Updated order with driver info: name=${updatedOrder.driverName}, id=${updatedOrder.driverId}")
                Result.success(updatedOrder)
            } else {
                android.util.Log.e("OrderRepository", "🔍 API Error: ${response.message()}, body=${response.errorBody()?.string()}")
                Result.failure(Exception(response.message() ?: "Failed to get order"))
            }
        } catch (e: Exception) {
            android.util.Log.e("OrderRepository", "🔍 Exception fetching order: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    suspend fun getOrderWithDriver(orderId: String): Result<OrderWithDriverResponse> {
        return try {
            val response = apiService.getOrder(orderId)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception(response.message() ?: "Failed to get order"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    suspend fun getActiveOrder(): Result<Order?> {
        return try {
            val response = apiService.getActiveOrder()
            if (response.isSuccessful && response.body() != null) {
                val activeOrder = response.body()!!
                Result.success(activeOrder)
            } else {
                Result.failure(Exception(response.message() ?: "Failed to get active order"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    suspend fun scheduleDelivery(orderId: String, request: ScheduleDeliveryRequest): Result<Order> {
        return try {
            val response = apiService.scheduleDelivery(orderId, request)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception(response.message() ?: "Failed to schedule delivery"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    suspend fun cancelOrder(orderId: String): Result<Order> {
        return try {
            val response = apiService.cancelOrder(orderId)
            if (response.isSuccessful && response.body() != null) {
                preferencesManager.saveActiveOrderId(null)
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception(response.message() ?: "Failed to cancel order"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    suspend fun getPricingInfo(fromLat: Double, fromLng: Double, toLat: Double, toLng: Double): Result<PricingInfo> {
        return try {
            val response = apiService.getPricingInfo(fromLat, fromLng, toLat, toLng)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception(response.message() ?: "Failed to get pricing info"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    suspend fun processPayment(orderId: String, request: PaymentRequest): Result<PaymentResponse> {
        return try {
            val response = apiService.processPayment(orderId, request)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception(response.message() ?: "Payment failed"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
    
    suspend fun submitReview(orderId: String, request: ReviewRequest): Result<ReviewResponse> {
        return try {
            val response = apiService.submitReview(orderId, request)
            if (response.isSuccessful && response.body() != null) {
                Result.success(response.body()!!)
            } else {
                Result.failure(Exception(response.message() ?: "Failed to submit review"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}

