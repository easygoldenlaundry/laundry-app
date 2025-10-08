# app/db_health.py
"""
Database health monitoring and connection management utilities.
"""
import logging
from typing import Optional
from sqlmodel import Session, text
from app.db import get_engine

logger = logging.getLogger(__name__)

def check_database_health() -> dict:
    """
    Check database connection health and return status information.
    """
    try:
        engine = get_engine()
        with Session(engine) as session:
            # Simple query to test connection
            result = session.exec(text("SELECT 1 as health_check")).first()
            
            # Get pool status
            pool = engine.pool
            pool_status = {
                "size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "invalid": pool.invalid()
            }
            
            return {
                "status": "healthy",
                "connection_test": "passed",
                "pool_status": pool_status
            }
    except Exception as e:
        logger.error(f"Database health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "pool_status": None
        }

def get_connection_pool_info() -> dict:
    """
    Get detailed information about the database connection pool.
    """
    try:
        engine = get_engine()
        pool = engine.pool
        
        return {
            "pool_size": pool.size(),
            "checked_in_connections": pool.checkedin(),
            "checked_out_connections": pool.checkedout(),
            "overflow_connections": pool.overflow(),
            "invalid_connections": pool.invalid(),
            "total_connections": pool.checkedin() + pool.checkedout(),
            "available_connections": pool.checkedin(),
            "utilization_percent": round((pool.checkedout() / pool.size()) * 100, 2) if pool.size() > 0 else 0
        }
    except Exception as e:
        logger.error(f"Failed to get pool info: {str(e)}")
        return {"error": str(e)}

def log_pool_status():
    """
    Log current pool status for monitoring.
    """
    pool_info = get_connection_pool_info()
    if "error" not in pool_info:
        logger.info(f"DB Pool Status: {pool_info['total_connections']} total, "
                   f"{pool_info['available_connections']} available, "
                   f"{pool_info['utilization_percent']}% utilized")
    else:
        logger.error(f"Failed to get pool status: {pool_info['error']}")
