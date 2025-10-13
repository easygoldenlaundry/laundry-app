# app/main.py
import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
import socketio

# Import from our app
from app.db import create_db_and_tables
from app.sockets import socketio_server
from app.sla import check_slas_periodically
from app.tasks import delete_old_messages_periodically, reset_monthly_trackers

from app.routes import (
    health, auth_pages, orders, queues, admin, driver, bags, 
    stations, admin_api, qa, book, track, claims, users, stations_pages,
    admin_dashboard, finance, location  # <<< NEW: Import location
)


# --- Logging Setup ---
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_file = os.path.join(LOG_DIR, "app.log")

file_handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=14)
file_handler.setFormatter(log_formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)

uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addHandler(file_handler)
uvicorn_error_logger = logging.getLogger("uvicorn.error")
uvicorn_error_logger.addHandler(file_handler)


# --- App Initialization ---
# 1. Create the FastAPI app instance first
fastapi_app = FastAPI()

# 2. Define startup events on the FastAPI instance
@fastapi_app.on_event("startup")
async def on_startup():
    root_logger.info("--- Application Starting Up ---")
    
    # Start database initialization in background to prevent blocking
    async def init_database():
        try:
            create_db_and_tables()
            root_logger.info("--- Database tables created ---")
        except Exception as e:
            root_logger.warning(f"Database initialization failed: {e}")
    
    # Start background tasks asynchronously
    async def start_background_tasks():
        try:
            asyncio.create_task(check_slas_periodically())
            asyncio.create_task(delete_old_messages_periodically())
            asyncio.create_task(reset_monthly_trackers())
            root_logger.info("--- Background tasks started ---")
        except Exception as e:
            root_logger.warning(f"Background task initialization failed: {e}")
    
    # Start both initialization tasks in parallel without blocking
    asyncio.create_task(init_database())
    asyncio.create_task(start_background_tasks())
    
    root_logger.info("--- Application startup complete (non-blocking) ---")

# Add shutdown event for graceful cleanup
@fastapi_app.on_event("shutdown")
async def on_shutdown():
    root_logger.info("--- Application Shutting Down ---")

# 3. Mount static files and include all routers on the FastAPI instance
fastapi_app.mount("/static", StaticFiles(directory="app/static"), name="static")
fastapi_app.mount("/data", StaticFiles(directory="data"), name="data")

fastapi_app.include_router(book.router) # Web routes - MUST be first for root redirect
fastapi_app.include_router(book.api_router) # Mobile API routes for booking
fastapi_app.include_router(health.router) # Health checks
fastapi_app.include_router(auth_pages.router)
fastapi_app.include_router(users.router) # Web routes
fastapi_app.include_router(users.api_router) # Mobile API routes for users
fastapi_app.include_router(track.router)
fastapi_app.include_router(claims.router)
fastapi_app.include_router(driver.router)
fastapi_app.include_router(location.router) # <<< NEW: Include location router
fastapi_app.include_router(stations_pages.router) 
fastapi_app.include_router(admin.router)
fastapi_app.include_router(admin_dashboard.router) 
fastapi_app.include_router(finance.html_router) 
fastapi_app.include_router(finance.router)
fastapi_app.include_router(orders.router)
fastapi_app.include_router(queues.router)
fastapi_app.include_router(bags.router)
fastapi_app.include_router(stations.router) 
fastapi_app.include_router(admin_api.router)
fastapi_app.include_router(qa.router)


# 4. Define middleware on the FastAPI instance
from app.auth import set_user_on_request_state
@fastapi_app.middleware("http")
async def add_user_to_state(request: Request, call_next):
    # Skip database operations for health checks and static files
    if request.url.path in ["/", "/health", "/health/database", "/ready"] or request.url.path.startswith("/static/"):
        response = await call_next(request)
        return response
    
    # Only run database operations for actual application requests
    try:
        from app.db import Session, engine
        with Session(engine) as session:
            await set_user_on_request_state(request, session)
            response = await call_next(request)
            return response
    except Exception as e:
        # If database fails, still allow the request to proceed
        root_logger.warning(f"Database middleware failed: {e}")
        response = await call_next(request)
        return response

# 5. Finally, create the main 'app' by wrapping the configured FastAPI app with Socket.IO
# This is the object that Uvicorn will run.
app = socketio.ASGIApp(socketio_server, other_asgi_app=fastapi_app)