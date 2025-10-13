# app/routes/health.py
from fastapi import APIRouter
from datetime import datetime, timezone
from app.db_health import check_database_health, get_connection_pool_info

router = APIRouter()

@router.get("/")
def root_health():
    """Simple root health check for Render.com"""
    return {"status": "ok", "message": "Server is running"}

@router.get("/health")
def get_health():
    """Returns the current status and time of the server."""
    # Simple health check without database operations to prevent timeouts
    return {
        "status": "ok",
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