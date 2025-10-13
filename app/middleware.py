# app/middleware.py
"""
Middleware for monitoring and managing database connections.
"""
import logging
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.db_health import log_pool_status

logger = logging.getLogger(__name__)

class DatabaseConnectionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to monitor database connection usage and log pool status.
    """
    
    def __init__(self, app, log_interval: int = 60):
        super().__init__(app)
        self.log_interval = log_interval
        self.last_log_time = 0
    
    async def dispatch(self, request: Request, call_next):
        # Log pool status periodically
        current_time = time.time()
        if current_time - self.last_log_time > self.log_interval:
            log_pool_status()
            self.last_log_time = current_time
        
        # Add connection pool info to response headers in development
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Add timing information
            process_time = time.time() - start_time
            response.headers["X-Process-Time"] = str(process_time)
            
            return response
            
        except Exception as e:
            logger.error(f"Request processing error: {str(e)}")
            raise
