# app/sockets.py
import socketio
import json
import logging
from sqlmodel import SQLModel

# Create the Socket.IO asynchronous server
socketio_server = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    # Add timeout configurations to prevent connection issues
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1000000,
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
    Emits an 'order.updated' event to relevant rooms.
    """
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
    for room in unique_rooms:
        await socketio_server.emit('order.updated', order_dict, room=room)
    
    logging.debug(f"Broadcasted update for order {order_id} to rooms: {list(unique_rooms)}")

async def broadcast_message_update(message_data: dict):
    """Emits a 'message.new' event to a specific order's room."""
    order_id = message_data.get("order_id")
    if not order_id:
        return

    room = f"order:{order_id}"
    await socketio_server.emit('message.new', message_data, room=room)
    logging.info(f"Broadcasted new message for order {order_id} to room {room}")

async def broadcast_admin_notification(event: str, data: dict = None):
    """Emits an event to the general admin room (hub:1)."""
    room = "hub:1"
    await socketio_server.emit(event, data, room=room)
    logging.info(f"Broadcasted admin notification '{event}' to room {room}")

async def broadcast_machine_update(machine):
    """
    Emits a 'machine.updated' event to relevant rooms.
    """
    machine_dict = model_to_dict(machine)
    if hasattr(machine, 'station') and machine.station:
        hub_id = machine.station.hub_id
        station_type = machine.station.type
    else:
        logging.warning(f"Machine {machine.id} does not have station data. Cannot broadcast update.")
        return 

    rooms = [
        f"hub:{hub_id}",
        f"machine:{machine.id}",
        f"station:{hub_id}:{station_type}"
    ]
    
    unique_rooms = set(rooms)
    for room in unique_rooms:
        await socketio_server.emit('machine.updated', machine_dict, room=room)
    
    logging.debug(f"Broadcasted update for machine {machine.id} to rooms: {list(unique_rooms)}")

# --- NEW FUNCTION ---
async def broadcast_driver_location_update(order_id: int, payload: dict):
    """Emits a 'driver.location_update' event to a specific order's room."""
    room = f"order:{order_id}"
    await socketio_server.emit('driver.location_update', payload, room=room)
    logging.debug(f"Broadcasted location for order {order_id} to room {room}")

async def broadcast_settings_update():
    """
    Emits a 'settings.updated' event to all connected clients.
    """
    # Send to all hubs (for now, just hub 1)
    room = "hub:1"
    await socketio_server.emit('settings.updated', {}, room=room)
    logging.info(f"Broadcasted settings update to room {room}")


@socketio_server.event
async def connect(sid, environ):
    try:
        logging.info(f"Socket connected: {sid}")
    except Exception as e:
        logging.error(f"Error in socket connect: {e}")

@socketio_server.event
async def disconnect(sid):
    try:
        logging.info(f"Socket disconnected: {sid}")
    except Exception as e:
        logging.error(f"Error in socket disconnect: {e}")

@socketio_server.event
async def join(sid, data):
    """Handle room joining with error handling"""
    try:
        room = data.get('room')
        if room:
            await socketio_server.enter_room(sid, room)
            logging.info(f"Socket {sid} joined room: {room}")
    except Exception as e:
        logging.error(f"Error joining room: {e}")

@socketio_server.on('join')
async def on_join(sid, data):
    room = data.get('room')
    if room:
        socketio_server.enter_room(sid, room)
        logging.info(f"Client {sid} joined room: {room}")

@socketio_server.on('leave')
async def on_leave(sid, data):
    room = data.get('room')
    if room:
        socketio_server.leave_room(sid, room)
        logging.info(f"Client {sid} left room: {room}")