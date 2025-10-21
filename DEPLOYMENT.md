# 🚀 Deployment Guide - Database Connection Optimization

## ⚡ Critical: Health Check Timeout Fix

**FIXED**: The app no longer runs the database seeder on startup, which was causing Render health checks to timeout.

- The seeder has been removed from `start.sh` to allow the server to start immediately
- Run `seed_only.sh` as a **one-time manual job** after deployment to initialize the database
- This prevents the 5-second health check timeout issue

## 🔧 Database Connection Issues Fixed

The "MaxClientsInSessionMode: max clients reached" error has been resolved with optimized database connection pooling.

## 📋 Environment Variables for Production

Add these environment variables to your production deployment (Render, Heroku, etc.):

### Required Environment Variables

```bash
# Database Configuration
ENVIRONMENT=production
DB_POOL_SIZE=3
DB_MAX_OVERFLOW=5
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800

# Your existing variables
DATABASE_URL=your_supabase_connection_string
JWT_SECRET_KEY=your_jwt_secret
ADMIN_SECRET=your_admin_secret

# Paystack Payment Configuration
PAYSTACK_SECRET_KEY=your_paystack_secret_key
PAYSTACK_WEBHOOK_URL=https://your-app.onrender.com/api/webhooks/paystack
```

### Development Environment Variables

```bash
# For local development
ENVIRONMENT=development
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=3600

# Paystack Payment Configuration (for testing)
PAYSTACK_SECRET_KEY=your_paystack_test_secret_key
PAYSTACK_WEBHOOK_URL=https://your-local-tunnel-url.ngrok.io/api/webhooks/paystack
```

## 🏥 Health Monitoring

### Database Health Check
- **Endpoint**: `/health/database`
- **Purpose**: Monitor database connection pool status
- **Response**: Connection pool utilization, health status

### Basic Health Check
- **Endpoint**: `/health`
- **Purpose**: Basic application health
- **Response**: Server status and timestamp

## 🔍 Connection Pool Settings Explained

### Production Settings (Conservative)
- **Pool Size**: 3 connections (matches Supabase Session mode limits)
- **Max Overflow**: 5 additional connections (total: 8 max)
- **Pool Timeout**: 30 seconds (wait time for connection)
- **Pool Recycle**: 30 minutes (connection lifetime)

### Development Settings (Permissive)
- **Pool Size**: 5 connections
- **Max Overflow**: 10 additional connections (total: 15 max)
- **Pool Timeout**: 30 seconds
- **Pool Recycle**: 1 hour

## 🚨 Troubleshooting

### If you still get connection errors:

1. **Reduce pool size further**:
   ```bash
   DB_POOL_SIZE=2
   DB_MAX_OVERFLOW=3
   ```

2. **Check Supabase dashboard** for active connections

3. **Monitor health endpoint**:
   ```bash
   curl https://your-app.com/health/database
   ```

4. **Check logs** for pool utilization warnings

## 📊 Monitoring Commands

### Check Database Health
```bash
curl https://your-app.com/health/database
```

### Expected Response
```json
{
  "database": {
    "status": "healthy",
    "connection_test": "passed",
    "pool_status": {
      "size": 3,
      "checked_in": 2,
      "checked_out": 1,
      "overflow": 0,
      "invalid": 0
    }
  },
  "connection_pool": {
    "pool_size": 3,
    "checked_in_connections": 2,
    "checked_out_connections": 1,
    "overflow_connections": 0,
    "invalid_connections": 0,
    "total_connections": 3,
    "available_connections": 2,
    "utilization_percent": 33.33
  },
  "timestamp": "2025-01-08T19:47:49.735828055Z"
}
```

## 🎯 Key Improvements Made

1. **Connection Pool Optimization**: Reduced pool size for Supabase Session mode
2. **Environment-Aware Configuration**: Different settings for dev/prod
3. **Connection Recycling**: Automatic connection cleanup
4. **Health Monitoring**: Real-time pool status monitoring
5. **Pre-ping Validation**: Ensures connections are valid before use
6. **UTC Timezone**: Consistent timezone handling

## 🔄 Deployment Steps

### Initial Deployment

1. **Set environment variables** in your deployment platform (Render/Heroku)
2. **Deploy the updated code**
3. **Run the database seeder as a one-time job**:
   - On Render: Create a manual job with command: `bash seed_only.sh`
   - Or use Shell: Connect to your instance and run `python -m app.seed_db`
4. **Monitor the health endpoint** for connection status
5. **Check logs** for any remaining connection issues

### On Render Specifically

**Important**: The seeder is NO LONGER run automatically on startup to prevent health check timeouts.

To initialize the database after deploying:
1. Go to your Render service dashboard
2. Click **Shell** (in the top right)
3. Run: `python -m app.seed_db`
4. Wait for completion (should take 10-30 seconds)
5. Your app is now ready!

**Note**: The seeder is idempotent - it only creates data if it doesn't exist, so it's safe to run multiple times.

### Health Check Configuration

Make sure your Render service has:
- **Health Check Path**: `/health`
- **Health Check Grace Period**: 60 seconds (to allow server startup)

The optimized configuration should resolve both the "max clients reached" error and health check timeout issues.
