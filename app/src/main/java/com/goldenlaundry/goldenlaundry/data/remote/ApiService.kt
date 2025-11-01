package com.goldenlaundry.goldenlaundry.data.remote

import com.goldenlaundry.goldenlaundry.data.model.*
import retrofit2.Response
import retrofit2.http.*

interface ApiService {
    
    // Authentication
    @POST("/api/customers/register")
    suspend fun register(@Body registerRequest: RegisterRequest): Response<AuthResponse>
    
    @POST("/api/auth/token/mobile")
    suspend fun login(@Body loginRequest: LoginRequest): Response<AuthResponse>
    
    @GET("/api/me")
    suspend fun getCurrentUser(): Response<User>
    
    @POST("/api/me/update")
    suspend fun updateProfile(@Body request: UpdateProfileRequest): Response<User>
    
    @DELETE("/api/me/delete-account")
    suspend fun deleteAccount(): Response<DeleteAccountResponse>
    
    // Orders
    @FormUrlEncoded
    @POST("/api/orders/book")
    suspend fun createBooking(
        @Field("pickup_address") pickupAddress: String,
        @Field("pickup_latitude") pickupLatitude: Double,
        @Field("pickup_longitude") pickupLongitude: Double,
        @Field("phone") phone: String,
        @Field("processing_option") processingOption: String,
        @Field("terms_accepted") termsAccepted: Boolean,
        @Field("distance_km") distanceKm: Double,
        @Field("pickup_cost") pickupCost: Double
    ): Response<BookingResponse>
    
    @GET("/api/orders/my-orders")
    suspend fun getMyOrders(): Response<List<Order>>
    
    @GET("/api/orders/{orderId}")
    suspend fun getOrder(@Path("orderId") orderId: String): Response<OrderWithDriverResponse>
    
    @GET("/api/orders/active")
    suspend fun getActiveOrder(): Response<Order>
    
    @POST("/api/orders/{orderId}/request-delivery")
    suspend fun scheduleDelivery(
        @Path("orderId") orderId: String,
        @Body request: ScheduleDeliveryRequest
    ): Response<Order>
    
    @POST("/api/orders/{orderId}/cancel")
    suspend fun cancelOrder(@Path("orderId") orderId: String): Response<Order>
    
    // Reviews
    @POST("/api/orders/{orderId}/submit-review")
    suspend fun submitReview(
        @Path("orderId") orderId: String,
        @Body request: ReviewRequest
    ): Response<ReviewResponse>
    
    // Payment
    @POST("/api/orders/{orderId}/process-payment")
    suspend fun processPayment(
        @Path("orderId") orderId: String,
        @Body request: PaymentRequest
    ): Response<PaymentResponse>
    
    // Chat - Updated to match existing backend API
    @GET("/api/orders/{orderId}/messages")
    suspend fun getChatMessages(@Path("orderId") orderId: String): Response<List<ChatMessage>>
    
    @POST("/api/orders/{orderId}/messages")
    suspend fun sendMessage(
        @Path("orderId") orderId: String,
        @Body request: SendMessageRequest
    ): Response<ChatMessage>
    
    @POST("/api/orders/{orderId}/messages/mark-read")
    suspend fun markMessagesAsRead(@Path("orderId") orderId: String): Response<Unit>
    
    // Pricing
    @GET("/api/pricing/calculate")
    suspend fun getPricingInfo(
        @Query("from_lat") fromLat: Double,
        @Query("from_lng") fromLng: Double,
        @Query("to_lat") toLat: Double,
        @Query("to_lng") toLng: Double
    ): Response<PricingInfo>
}

@com.squareup.moshi.JsonClass(generateAdapter = true)
data class PaymentResponse(
    @com.squareup.moshi.Json(name = "success") val success: Boolean,
    @com.squareup.moshi.Json(name = "message") val message: String,
    @com.squareup.moshi.Json(name = "order_id") val orderId: String,
    @com.squareup.moshi.Json(name = "amount") val amount: Double,
    @com.squareup.moshi.Json(name = "payment_method") val paymentMethod: String
)

@com.squareup.moshi.JsonClass(generateAdapter = true)
data class DeleteAccountResponse(
    @com.squareup.moshi.Json(name = "success") val success: Boolean,
    @com.squareup.moshi.Json(name = "message") val message: String
)

