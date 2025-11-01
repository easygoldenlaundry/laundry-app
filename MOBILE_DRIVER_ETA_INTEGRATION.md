# 📱 Mobile Driver App - ETA Integration Guide

## Overview
The driver app must send accurate ETA data using Mapbox routing information to provide customers with real-time delivery estimates. This guide explains exactly how to implement this integration.

## 🔑 API Endpoint

**Endpoint:** `POST /api/driver/mobile/location`
**Authentication:** Bearer Token (from login)
**Frequency:** Every 20 seconds while driver is active

## 📤 Request Format

### Required Fields
```json
{
    "lat": -26.204102,    // Driver's current latitude
    "lon": 28.047305      // Driver's current longitude
}
```

### Optional Fields (HIGHLY RECOMMENDED)
```json
{
    "lat": -26.204102,
    "lon": 28.047305,
    "mapbox_eta_minutes": 15,    // Mapbox ETA in minutes
    "mapbox_distance_km": 8.5    // Mapbox route distance in km
}
```

## 🎯 Mapbox Integration Steps

### 1. Get Route Information
Call Mapbox Directions API when driver starts navigation to destination:

```javascript
// When driver accepts job and starts navigation
async function getMapboxRoute(driverLat, driverLon, destLat, destLon) {
    const response = await fetch(
        `https://api.mapbox.com/directions/v5/mapbox/driving-traffic/${driverLon},${driverLat};${destLon},${destLat}?` +
        `access_token=${MAPBOX_ACCESS_TOKEN}&` +
        `geometries=geojson&` +
        `overview=full&` +
        `steps=true`
    );

    const data = await response.json();
    const route = data.routes[0];

    return {
        etaMinutes: Math.ceil(route.duration / 60), // Convert seconds to minutes
        distanceKm: route.distance / 1000,          // Convert meters to km
        route: route                                 // Store full route for navigation
    };
}
```

### 2. Send Location + ETA Data
Every 20 seconds, send current location with Mapbox ETA:

```javascript
async function sendLocationUpdate() {
    const position = await getCurrentPosition();

    // Get latest Mapbox ETA (if route is active)
    let mapboxData = {};
    if (currentRoute) {
        try {
            const routeInfo = await getMapboxRoute(
                position.coords.latitude,
                position.coords.longitude,
                destinationLat,
                destinationLon
            );
            mapboxData = {
                mapbox_eta_minutes: routeInfo.etaMinutes,
                mapbox_distance_km: routeInfo.distanceKm
            };
        } catch (error) {
            console.warn('Mapbox ETA failed, using fallback:', error);
            // mapboxData remains empty, server will use 35km/h fallback
        }
    }

    const locationData = {
        lat: position.coords.latitude,
        lon: position.coords.longitude,
        ...mapboxData  // Include Mapbox data if available
    };

    await fetch('/api/driver/mobile/location', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(locationData)
    });
}

// Send every 20 seconds
setInterval(sendLocationUpdate, 20000);
```

## 📥 Response Format

### Success Response
```json
{
    "has_active_job": true,
    "order_id": 456,
    "status": "OnRouteToCustomer",
    "progress": 75.2,              // Progress percentage (0-100)
    "eta_minutes": 15,             // ETA used by server (Mapbox or fallback)
    "current_distance_km": 8.5,    // Straight-line distance remaining
    "destination_type": "delivery", // "pickup" or "delivery"
    "eta_source": "mapbox"         // "mapbox" or "fallback"
}
```

### No Active Job
```json
{
    "has_active_job": false,
    "message": "Location updated"
}
```

## 🔄 When to Update Mapbox ETA

### Trigger Mapbox Route Calculation:
- ✅ When driver accepts a pickup job
- ✅ When driver picks up order and starts delivery
- ✅ When destination changes (rare)
- ✅ Every 5 minutes during long routes (optional optimization)

### Don't Update Mapbox Route:
- ❌ On every location update (too expensive)
- ❌ When GPS accuracy is poor
- ❌ When driver is not navigating

## 🛡️ Error Handling

### Mapbox API Failures
```javascript
try {
    const routeInfo = await getMapboxRoute(lat, lon, destLat, destLon);
    // Use Mapbox data
} catch (error) {
    console.warn('Mapbox failed, sending location without ETA');
    // Send location without mapbox_eta_minutes/mapbox_distance_km
    // Server automatically uses 35km/h fallback
}
```

### Network Issues
- Continue sending basic location data (lat/lon only)
- Server provides fallback ETA
- Retry Mapbox calls when connection restored

### GPS Issues
- Send last known good location
- Include accuracy data if available
- Server handles coordinate validation

## 📊 ETA Accuracy Comparison

| Scenario | Mapbox ETA | 35km/h Fallback |
|----------|------------|-----------------|
| City traffic | 25 minutes | 15 minutes ❌ |
| Highway | 12 minutes | 18 minutes ❌ |
| Rush hour | 45 minutes | 15 minutes ❌ |
| No traffic | 8 minutes | 12 minutes ⚠️ |

## 🔧 Implementation Checklist

### Required:
- [ ] GPS location permissions
- [ ] Bearer token authentication
- [ ] 20-second location update timer
- [ ] Basic lat/lon sending

### Recommended:
- [ ] Mapbox Directions API integration
- [ ] Route recalculation on job acceptance
- [ ] Error handling for API failures
- [ ] Offline location queuing

### Optional:
- [ ] Dynamic route updates during navigation
- [ ] ETA accuracy analytics
- [ ] Battery optimization for background updates

## 🚀 Quick Start Code (Android/Kotlin)

```kotlin
class LocationService : Service() {
    private val handler = Handler(Looper.getMainLooper())
    private val locationRunnable = object : Runnable {
        override fun run() {
            sendLocationUpdate()
            handler.postDelayed(this, 20000) // 20 seconds
        }
    }

    private fun sendLocationUpdate() {
        fusedLocationClient.lastLocation.addOnSuccessListener { location ->
            val locationData = JSONObject().apply {
                put("lat", location.latitude)
                put("lon", location.longitude)

                // Add Mapbox ETA if available
                currentMapboxEta?.let { put("mapbox_eta_minutes", it) }
                currentMapboxDistance?.let { put("mapbox_distance_km", it) }
            }

            sendToServer(locationData)
        }
    }

    private fun sendToServer(locationData: JSONObject) {
        val request = Request.Builder()
            .url("https://your-api.com/api/driver/mobile/location")
            .post(RequestBody.create(
                "application/json".toMediaType(),
                locationData.toString()
            ))
            .addHeader("Authorization", "Bearer $authToken")
            .build()

        client.newCall(request).enqueue(object : Callback {
            override fun onResponse(call: Call, response: Response) {
                // Handle success
            }

            override fun onFailure(call: Call, e: IOException) {
                // Handle failure - server will use fallback ETA
            }
        })
    }
}
```

## 📞 Support

If you encounter issues:
1. Check server logs for error messages
2. Verify Mapbox API key and quotas
3. Test with basic location data first (without Mapbox)
4. Ensure proper error handling for network failures

**Priority:** Always send location data, even if Mapbox fails. The server provides reliable fallback ETA.
