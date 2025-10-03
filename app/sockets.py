# app/sockets.py
import socketio
import json
import logging
from sqlmodel import SQLModel

# Create the Socket.IO asynchronous server
socketio_server = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
)

def model_to_dict(model_instance: SQLModel) -> dict:
    """Converts a SQLModel instance to a dictionary."""
    return json.loads(model_instance.json())


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


@socketio_server.event
async def connect(sid, environ):
    logging.info(f"Socket connected: {sid}")

@socketio_server.event
async def disconnect(sid):
    logging.info(f"Socket disconnected: {sid}")

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