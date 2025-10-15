# Bits-Layer Laundry Management System

A comprehensive laundry management system with real-time order tracking, station workflow management, and mobile app integration.

## 🚨 Critical Fix Applied: Station Crash Resolution

**Status:** ✅ **COMPLETED AND PRODUCTION READY**

The render.com server was crashing when orders moved through station workflows due to race conditions and transaction management issues. This has been completely fixed with robust error handling, row-level locking, and automatic retry logic.

### Key Fixes Applied
- ✅ **Database Transaction Safety** - Changed from AUTOCOMMIT to READ COMMITTED isolation
- ✅ **Row-Level Locking** - Prevents race conditions between concurrent station devices
- ✅ **Automatic Retry Logic** - Up to 3 retries with exponential backoff on conflicts
- ✅ **Comprehensive Error Handling** - Zero crashes from station operations
- ✅ **Robust Real-time Updates** - Socket broadcasts separated from database transactions
- ✅ **Connection Pool Monitoring** - Automatic health checks and stale connection cleanup

### Files Modified
- `app/db.py` - Database configuration and pool monitoring
- `app/services/state_machine.py` - Safe transaction handling
- `app/routes/stations.py` - Complete rewrite with locking and error handling
- `app/sockets.py` - Robust broadcast error handling
- `app/main.py` - Added connection pool monitoring

### Zero Breaking Changes
- ✅ All APIs unchanged
- ✅ Mobile apps compatible
- ✅ No database migrations
- ✅ WebSocket protocol same

## Quick Start

### Prerequisites
- Python 3.9+
- PostgreSQL/Supabase database
- Node.js (for frontend assets)

### Installation

1. **Clone and setup:**
   ```bash
   git clone <repository-url>
   cd Bits-Layer
   python -m venv venv
   source venv/Scripts/activate  # Windows
   pip install -r requirements.txt
   ```

2. **Environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your database URL and secrets
   ```

3. **Database setup:**
   ```bash
   python app/seed_db.py
   ```

4. **Run development server:**
   ```bash
   python run_dev.py
   ```

### Testing the Fixes

Run the robustness test suite:
```bash
python test_station_robustness.py
```

This tests:
- ✅ Concurrent station operations (no race conditions)
- ✅ Connection pool health under load
- ✅ Error recovery and retry logic

## Architecture

### Core Components

- **FastAPI Backend** - REST APIs and WebSocket support
- **SQLModel/SQLAlchemy** - Database ORM with PostgreSQL
- **Socket.IO** - Real-time communication
- **Jinja2 Templates** - Server-side rendered web pages
- **Mobile API** - REST endpoints for Android/iOS apps

### Key Features

- **Order Management** - Full lifecycle from booking to delivery
- **Station Workflow** - Hub pickup → Imaging → Processing → QA → Delivery
- **Real-time Updates** - Live status updates across all clients
- **Multi-tenant** - Support for multiple hubs/locations
- **Finance Integration** - Cost tracking and payment processing
- **User Management** - Admin, driver, and customer roles

### Station Workflow

1. **Hub Pickup** - Drivers collect laundry from customers
2. **Imaging** - Photos captured for quality control
3. **Pretreat** - Initial treatment and sorting
4. **Washing** - Main wash cycles with machine tracking
5. **Drying** - Drying cycles with energy monitoring
6. **Folding** - Manual folding station
7. **QA** - Quality assurance and final checks
8. **Ready for Delivery** - Order prepared for pickup
9. **Out for Delivery** - Driver assigned for delivery
10. **Delivered** - Order completed

## Production Deployment

### Render.com Setup

1. **Connect Repository** - Link your GitHub repo to Render
2. **Environment Variables:**
   ```bash
   DATABASE_URL=postgresql://...
   ENVIRONMENT=production
   JWT_SECRET_KEY=your-secret-key
   ADMIN_SECRET=your-admin-secret
   DB_POOL_SIZE=5
   DB_MAX_OVERFLOW=10
   ```
3. **Deploy** - Render auto-deploys on git push

### Monitoring

**Key Log Messages to Monitor:**
```bash
# ✅ Good signs
"Pool status: X connections"           # Every 60s
"transitioned to"                      # State changes working
"Broadcasted update"                   # Real-time updates working

# ⚠️ Normal under load
"lock conflict, retrying"              # Auto-recovery working
"Pool near capacity"                   # Monitor frequency

# 🚨 Investigate these
"Failed to commit"                     # Transaction issues
"Critical error"                       # Unexpected errors
```

### Health Checks

```bash
# Basic health
curl https://your-app.onrender.com/health

# Database health
curl https://your-app.onrender.com/health/database
```

## Development

### Project Structure

```
Bits-Layer/
├── app/
│   ├── db.py                    # Database configuration & pool monitoring
│   ├── main.py                  # FastAPI app & startup tasks
│   ├── sockets.py              # WebSocket server & broadcasts
│   ├── models.py               # SQLModel database models
│   ├── config.py               # Environment configuration
│   ├── routes/                 # API endpoint modules
│   │   ├── stations.py         # Station operations (FIXED)
│   │   ├── orders.py           # Order management
│   │   ├── queues.py           # Station queues
│   │   ├── driver.py           # Driver APIs
│   │   └── ...
│   ├── services/               # Business logic
│   │   ├── state_machine.py    # Order state transitions (FIXED)
│   │   ├── dispatch.py         # Driver dispatch logic
│   │   └── ...
│   ├── static/                 # Static assets (CSS/JS)
│   └── templates/              # Jinja2 templates
├── data/                       # File uploads (images/orders)
├── logs/                       # Application logs
├── tests/                      # Test suites
└── docs/                       # Documentation
```

### API Documentation

Once running, visit `/docs` for interactive API documentation.

### Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_orders_flow.py

# Run with coverage
pytest --cov=app --cov-report=html
```

## Troubleshooting

### Common Issues

**Station Operations Failing:**
- Check database connection pool logs
- Look for "lock conflict" messages (normal)
- Ensure `DB_POOL_SIZE` is appropriate for load

**Real-time Updates Not Working:**
- Check WebSocket connection logs
- Verify socket.io client configuration
- Look for broadcast error messages

**High Memory/CPU Usage:**
- Monitor connection pool size
- Check for memory leaks in background tasks
- Review database query performance

### Logs Location

- **Application Logs:** `logs/app.log`
- **Render Logs:** Dashboard → Logs tab
- **Database Logs:** Supabase dashboard

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with comprehensive tests
4. Ensure all tests pass
5. Submit a pull request

## License

[Your License Here]

## Support

For issues related to:
- **Station crashes/fixes:** See `STATION_CRASH_FIXES.md`
- **Deployment:** See `DEPLOYMENT_CHECKLIST.md`
- **API usage:** Check `/docs` endpoint
- **Database issues:** Check `logs/app.log`

---

## Recent Updates

**October 15, 2025** - **Station Crash Fixes Deployed**
- Fixed render.com server crashes during station operations
- Added row-level locking to prevent race conditions
- Implemented automatic retry logic and error recovery
- Enhanced real-time update reliability
- Added connection pool monitoring

**Status:** Production Ready ✅
