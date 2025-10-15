# 🚀 Render.com Deployment Checklist - Station Crash Fixes

## Pre-Deployment Verification

### ✅ Code Changes Complete
- [x] Fixed database isolation level (AUTOCOMMIT → READ COMMITTED)
- [x] Added row-level locking to all station endpoints
- [x] Implemented comprehensive error handling with retry logic
- [x] Separated socket broadcasts from database transactions
- [x] Enhanced socket broadcast error handling
- [x] Added connection pool monitoring background task
- [x] All lint errors resolved

### ✅ Files Modified
1. **app/db.py** - Database engine configuration and connection pool monitoring
2. **app/services/state_machine.py** - Transaction safety and broadcast scheduling
3. **app/routes/stations.py** - Complete rewrite with locking and error handling
4. **app/sockets.py** - Robust broadcast error handling
5. **app/main.py** - Added pool monitor to startup tasks

### ✅ No Breaking Changes
- All API endpoints unchanged
- WebSocket protocol unchanged
- No database schema changes required
- Compatible with existing mobile apps

## Deployment Steps

### 1. Commit and Push Changes
```bash
git add .
git commit -m "Fix station crashes with transaction management and row-level locking"
git push origin main
```

### 2. Deploy to Render.com
- Render will automatically deploy from main branch
- Monitor deployment logs for successful startup
- Look for: "Background tasks started (including pool monitor)"

### 3. Verify Environment Variables (on Render)
Ensure these are set:
- `DATABASE_URL` - Your Supabase connection string
- `ENVIRONMENT=production`
- `DB_POOL_SIZE=5` (optional, defaults to 5)
- `DB_MAX_OVERFLOW=10` (optional, defaults to 10)

### 4. Monitor Initial Startup
Watch for these log messages:
```
✅ "Database tables created"
✅ "Background tasks started (including pool monitor)"
✅ "Pool status: X connections"
✅ "Connection health check passed"
```

## Post-Deployment Testing

### 1. Health Checks
```bash
# Replace with your render.com URL
curl https://your-app.onrender.com/health
curl https://your-app.onrender.com/health/database
```

Expected: Both return 200 OK

### 2. Test Station Operations (Manual)
1. Open a station page (e.g., Pretreat)
2. Start a cycle on a basket
3. ✅ Should succeed without errors
4. Open same station in another tab
5. Try to start cycle on same basket
6. ✅ Should see "No free machines" or graceful handling

### 3. Test Concurrent Operations (Optional)
```bash
# On your local machine
python test_station_robustness.py
```

Update `BASE_URL` in the script to your render.com URL.

### 4. Monitor Production Logs

#### Watch for Success Indicators:
```bash
# On Render dashboard → Logs
grep "Pool status" logs     # Every 60s
grep "transitioned to" logs # Successful state changes
grep "Broadcasted update" logs # Socket updates working
```

#### Watch for Warning Indicators (Normal Under Load):
```bash
grep "lock conflict" logs   # Should auto-retry and succeed
grep "retrying" logs        # Expected, shows retry logic working
grep "Pool near capacity" logs # Monitor if this appears frequently
```

#### Watch for Error Indicators (Investigate):
```bash
grep "Failed to commit" logs    # Should be rare
grep "Critical error" logs      # Should not appear
grep "500" logs                 # Internal errors
```

## Success Criteria

### ✅ No Crashes
- Server stays up when processing multiple orders
- No restarts from station operations
- No 502/503 errors (except transient)

### ✅ Concurrent Operations Work
- Multiple station devices can operate simultaneously
- Race conditions handled gracefully
- Lock conflicts automatically retry

### ✅ Real-time Updates
- Station screens update instantly
- Mobile apps receive live order updates
- No broadcast failures causing crashes

### ✅ Pool Health
- Connection count stays under limit
- Stale connections automatically cleaned
- No connection leaks

## Monitoring (First 24 Hours)

### Key Metrics to Watch

1. **Request Success Rate**
   - Target: >99% (excluding legitimate 404s)
   - Look at Render dashboard metrics

2. **Response Times**
   - Average: <500ms for station endpoints
   - P99: <2s (includes retries)

3. **Error Rates**
   - 500 errors: Should be near zero
   - 503 errors: Occasional OK (means retry logic triggered)
   - 409 errors: Normal (concurrent machine conflicts)

4. **Connection Pool**
   - Look for hourly "Pool status" logs
   - Active connections should stay under 12 (out of 15 max)

5. **Memory/CPU (Render Dashboard)**
   - Should remain stable
   - No memory leaks
   - CPU spikes OK during high load

## Rollback Plan (If Needed)

If critical issues arise:

1. **Quick Rollback on Render:**
   ```bash
   git revert HEAD
   git push origin main
   ```

2. **Or Manual Rollback on Render Dashboard:**
   - Go to your service
   - Click "Manual Deploy"
   - Select previous successful deployment

3. **Revert Locally:**
   ```bash
   git reset --hard HEAD~1
   git push -f origin main
   ```

## Known Acceptable Behaviors

### ✅ Normal/Expected:
- "Database lock conflict, retrying..." (auto-recovers)
- "Failed to broadcast to room" (doesn't affect operation)
- Occasional 503 under very high load (client should retry)
- "Pool near capacity" warnings during peak times

### ⚠️ Investigate If Frequent:
- Multiple failed retries for same operation
- Consistent 503 errors
- "Pool at capacity" constantly
- Socket broadcast failures >10% of time

### 🚨 Critical - Immediate Action:
- Server crashes/restarts
- Database connection errors not recovering
- All requests failing
- Memory/CPU at 100% sustained

## Optimization Opportunities (Future)

If you experience high load:

1. **Increase Pool Size** (if Supabase allows):
   ```python
   DB_POOL_SIZE = 10
   DB_MAX_OVERFLOW = 20
   ```

2. **Add Redis for Socket.io** (scale to millions):
   ```python
   # In app/sockets.py
   mgr = socketio.AsyncRedisManager('redis://redis-url')
   socketio_server = socketio.AsyncServer(client_manager=mgr, ...)
   ```

3. **Add Caching** for read-heavy endpoints:
   ```python
   from functools import lru_cache
   
   @lru_cache(maxsize=1000)
   def get_settings():
       ...
   ```

4. **Horizontal Scaling** on Render:
   - Enable multiple instances
   - Requires Redis for Socket.io
   - Load balancer handles distribution

## Support Contacts

- **Database Issues:** Check Supabase dashboard
- **Deployment Issues:** Render.com support
- **Application Issues:** Check logs first, then code

## Success! 🎉

If you see:
- ✅ No crashes after 24 hours
- ✅ Station operations working smoothly
- ✅ Concurrent operations handled gracefully
- ✅ Real-time updates working
- ✅ Pool health stable

**Congratulations!** Your render.com deployment is now **production-ready and robust**.

---

## Quick Reference

### Most Important Log Lines to Monitor

```bash
# Good signs:
"transitioned to"           # State changes working
"Pool status: X connections" # Pool healthy
"Connection health check passed" # DB connection OK

# Watch these:
"lock conflict, retrying"   # Normal, should succeed
"Pool near capacity"        # Monitor frequency
"Failed to broadcast"       # OK if <5% of operations

# Bad signs (investigate):
"Failed to commit"          # Transaction issues
"Critical error"            # Unexpected errors
"Database busy, please try again" # Pool exhausted
```

### Quick Health Check Command

```bash
# One-liner to check if everything is working
curl https://your-app.onrender.com/health && \
curl https://your-app.onrender.com/health/database && \
echo "✅ All healthy!"
```

---

**Last Updated:** October 15, 2025
**Version:** 2.0 (Station Crash Fixes)

