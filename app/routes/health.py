# app/routes/health.py
from fastapi import APIRouter
from datetime import datetime, timezone
from app.db_health import check_database_health, get_connection_pool_info

router = APIRouter()

@router.get("/health")
def get_health():
    """Returns the current status and time of the server."""
    # Try to wake up database by testing connection
    try:
        from app.db_health import check_database_health
        db_status = check_database_health()
        health_status = "ok" if db_status["status"] == "healthy" else "degraded"
    except Exception:
        health_status = "ok"  # Don't fail health check due to DB issues

    return {
        "status": health_status,
        "time": datetime.now(timezone.utc).isoformat()
    }

@router.get("/health/database")
def get_database_health():
    """Returns database health status and connection pool information."""
    db_health = check_database_health()
    pool_info = get_connection_pool_info()
    
    return {
        "database": db_health,
        "connection_pool": pool_info,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }