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

# --- THIS IS THE FIX: Simplified and corrected router imports ---
from app.routes import (
    health, auth_pages, orders, queues, admin, driver, bags, 
    stations, admin_api, qa, book, track, claims, users, stations_pages,
    admin_dashboard
)


# --- Logging Setup ---
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Configure the formatter
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_file = os.path.join(LOG_DIR, "app.log")

# Rotating file handler (5MB per file, keep last 14 files)
file_handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=14)
file_handler.setFormatter(log_formatter)

# Get the root logger and add our file handler
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)

# Also capture logs from uvicorn and send them to our file
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.addHandler(file_handler)
uvicorn_error_logger = logging.getLogger("uvicorn.error")
uvicorn_error_logger.addHandler(file_handler)


# --- App Initialization ---
app = FastAPI()

# --- Mount the Socket.IO app ---
# This creates a combined ASGI app that handles both HTTP and WebSocket traffic
socket_app = socketio.ASGIApp(socketio_server, other_asgi_app=app)

@app.on_event("startup")
def on_startup():
    root_logger.info("--- Application Starting Up ---")
    # This will create the db and tables if they don't exist
    create_db_and_tables()
    # Start the background SLA checker
    asyncio.create_task(check_slas_periodically())
    root_logger.info("--- Database and background tasks initialized ---")

# --- Static Files ---
# This will serve files from the 'app/static' directory
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/data", StaticFiles(directory="data"), name="data")

# --- THIS IS THE FIX: Correctly ordered and named router registration ---
app.include_router(health.router)
app.include_router(auth_pages.router)
app.include_router(users.router)
app.include_router(book.router)
app.include_router(track.router)
app.include_router(claims.router)
app.include_router(driver.router)
# Staff/Admin Pages (No prefix)
app.include_router(stations_pages.router) 
# Admin-Only Pages (Prefix is /admin)
app.include_router(admin.router)
app.include_router(admin_dashboard.router) 
# API Routers
app.include_router(orders.router)
app.include_router(queues.router)
app.include_router(bags.router)
app.include_router(stations.router) 
app.include_router(admin_api.router)
app.include_router(qa.router)


# --- Add user to request state ---
# This middleware makes the user object available in all templates
from app.auth import set_user_on_request_state
@app.middleware("http")
async def add_user_to_state(request: Request, call_next):
    # The dependency injection system for get_current_user needs the db session,
    # but middleware runs before that. So we manually create a session here.
    from app.db import Session, engine
    with Session(engine) as session:
        await set_user_on_request_state(request, session)
        response = await call_next(request)
        return response