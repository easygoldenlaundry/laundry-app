# app/sockets.py
import socketio
import json
import logging
from sqlmodel import SQLModel

logger = logging.getLogger(__name__)

# Create the Socket.IO asynchronous server
# OPTIMIZED FOR RENDER.COM + REALTIME STATION UPDATES + MILLIONS OF CLIENTS
socketio_server = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    # Optimized for instant updates with many concurrent connections
    ping_timeout=15,        # Slightly increased for reliability under load
    ping_interval=8,        # Balanced for instant updates and server load
    max_http_buffer_size=1000000,
    # Connection settings for high concurrency
    always_connect=True,
    transports=['websocket', 'polling'],
    # Async mode settings for better performance
    engineio_logger=False,  # Reduce logging overhead
    logger=False,           # Reduce logging overhead
    # Allow reconnections
    allow_upgrades=True,
    # Increase max connections
    async_handlers=True
)

def model_to_dict(model_instance: SQLModel) -> dict:
    """
    Converts a SQLModel instance to a dictionary.
    Excludes relationships to avoid triggering lazy loading (N+1 queries).
    """
    # Define relationships to exclude for common models
    exclude_relations = {
        'claims', 'events', 'images', 'messages', 'finance_entries',
        'customer', 'bags', 'baskets', 'order'
    }
    return json.loads(model_instance.json(exclude=exclude_relations))


async def broadcast_order_update(order):
    """
    Emits an 'order.updated' event to relevant rooms with robust error handling.
    Designed to work with 1-2 station devices and millions of mobile clients.
    """
    try:
        order_dict = model_to_dict(order)
        hub_id = order.hub_id
        status = order.status
        order_id = order.id

        PREVIOUS_STATION_MAP = {
            "Imaging": "DeliveredToHub", 
            "Washing": "Pretreat",
            "Drying": "washing",
            "Folding": "drying",
            "QA": "folding",
        }

        rooms = [
            f"hub:{hub_id}",
            f"order:{order_id}",
            f"station:{hub_id}:{status}" 
        ]
        
        previous_station_type = PREVIOUS_STATION_MAP.get(status)
        if previous_station_type:
            rooms.append(f"station:{hub_id}:{previous_station_type}")

        if order.assigned_driver_id:
            rooms.append(f"driver:{order.assigned_driver_id}")

        unique_rooms = set(rooms)
        
        # Broadcast to each room independently with error handling
        broadcast_errors = []
        for room in unique_rooms:
            try:
                await socketio_server.emit('order.updated', order_dict, room=room)
            except Exception as room_error:
                broadcast_errors.append(f"{room}: {str(room_error)}")
                logger.warning(f"Failed to broadcast to room {room}: {room_error}")
        
        if broadcast_errors:
            logger.warning(f"Order {order_id} broadcast had {len(broadcast_errors)} room failures")
        else:
            logger.debug(f"Broadcasted update for order {order_id} to {len(unique_rooms)} rooms")
            
    except Exception as e:
        logger.error(f"Critical error broadcasting order update for order {order.id}: {e}")
        # Don't raise - broadcast failures shouldn't break the application

async def broadcast_message_update(message_data: dict):
    """Emits a 'message.new' event to a specific order's room."""
    try:
        order_id = message_data.get("order_id")
        if not order_id:
            return

        room = f"order:{order_id}"
        await socketio_server.emit('message.new', message_data, room=room)
        logger.info(f"Broadcasted new message for order {order_id} to room {room}")
    except Exception as e:
        logger.error(f"Failed to broadcast message update: {e}")

async def broadcast_admin_notification(event: str, data: dict = None):
    """Emits an event to the general admin room (hub:1)."""
    try:
        room = "hub:1"
        await socketio_server.emit(event, data, room=room)
        logger.info(f"Broadcasted admin notification '{event}' to room {room}")
    except Exception as e:
        logger.error(f"Failed to broadcast admin notification: {e}")

async def broadcast_machine_update(machine):
    """
    Emits a 'machine.updated' event to relevant rooms with robust error handling.
    Critical for realtime station device updates (1-2 devices per station).
    """
    try:
        machine_dict = model_to_dict(machine)
        if hasattr(machine, 'station') and machine.station:
            hub_id = machine.station.hub_id
            station_type = machine.station.type
        else:
            logger.warning(f"Machine {machine.id} does not have station data. Cannot broadcast update.")
            return 

        rooms = [
            f"hub:{hub_id}",
            f"machine:{machine.id}",
            f"station:{hub_id}:{station_type}"
        ]
        
        unique_rooms = set(rooms)
        
        # Broadcast to each room independently with error handling
        broadcast_errors = []
        for room in unique_rooms:
            try:
                await socketio_server.emit('machine.updated', machine_dict, room=room)
            except Exception as room_error:
                broadcast_errors.append(f"{room}: {str(room_error)}")
                logger.warning(f"Failed to broadcast machine update to room {room}: {room_error}")
        
        if broadcast_errors:
            logger.warning(f"Machine {machine.id} broadcast had {len(broadcast_errors)} room failures")
        else:
            logger.debug(f"Broadcasted update for machine {machine.id} to {len(unique_rooms)} rooms")
            
    except Exception as e:
        logger.error(f"Critical error broadcasting machine update for machine {machine.id}: {e}")
        # Don't raise - broadcast failures shouldn't break the application

# --- NEW FUNCTION ---
async def broadcast_driver_location_update(order_id: int, payload: dict):
    """Emits a 'driver.location_update' event to a specific order's room."""
    try:
        room = f"order:{order_id}"
        await socketio_server.emit('driver.location_update', payload, room=room)
        logger.debug(f"Broadcasted location for order {order_id} to room {room}")
    except Exception as e:
        logger.error(f"Failed to broadcast driver location: {e}")

async def broadcast_settings_update():
    """
    Emits a 'settings.updated' event to all connected clients.
    """
    try:
        # Send to all hubs (for now, just hub 1)
        room = "hub:1"
        await socketio_server.emit('settings.updated', {}, room=room)
        logger.info(f"Broadcasted settings update to room {room}")
    except Exception as e:
        logger.error(f"Failed to broadcast settings update: {e}")


@socketio_server.event
async def connect(sid, environ):
    """Handle client connection with error handling"""
    try:
        logger.info(f"Socket connected: {sid}")
    except Exception as e:
        logger.error(f"Error in socket connect: {e}")

@socketio_server.event
async def disconnect(sid):
    """Handle client disconnection with error handling"""
    try:
        logger.info(f"Socket disconnected: {sid}")
    except Exception as e:
        logger.error(f"Error in socket disconnect: {e}")

@socketio_server.event
async def join(sid, data):
    """Handle room joining with error handling"""
    try:
        room = data.get('room')
        if room:
            await socketio_server.enter_room(sid, room)
            logger.debug(f"Socket {sid} joined room: {room}")
    except Exception as e:
        logger.error(f"Error joining room: {e}")

@socketio_server.on('join')
async def on_join(sid, data):
    """Handle explicit join event"""
    try:
        room = data.get('room')
        if room:
            await socketio_server.enter_room(sid, room)
            logger.debug(f"Client {sid} joined room: {room}")
    except Exception as e:
        logger.error(f"Error in join handler: {e}")

@socketio_server.on('leave')
async def on_leave(sid, data):
    """Handle explicit leave event"""
    try:
        room = data.get('room')
        if room:
            await socketio_server.leave_room(sid, room)
            logger.debug(f"Client {sid} left room: {room}")
    except Exception as e:
        logger.error(f"Error in leave handler: {e}")