# app/sockets.py
import socketio
import json
import logging
from sqlmodel import SQLModel

# Create the Socket.IO asynchronous server
socketio_server = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=[]
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

    # --- FIX: More robust logic for notifying previous stations to refresh their queues ---
    # This map defines which station to notify when an order ENTERS a new status.
    # For example, when an order's status becomes "Drying", we notify the "washing" station.
    PREVIOUS_STATION_MAP = {
        "Imaging": "DeliveredToHub", # For the intake screen
        "Washing": "Pretreat",
        "Drying": "washing",
        "Folding": "drying",
        "QA": "folding",
    }

    # Define the base rooms for this update
    rooms = [
        f"hub:{hub_id}",
        f"order:{order_id}",
        f"station:{hub_id}:{status}" # Notify the station for the order's NEW status
    ]
    
    # Check the map to see if we also need to notify the PREVIOUS station
    previous_station_type = PREVIOUS_STATION_MAP.get(status)
    if previous_station_type:
        rooms.append(f"station:{hub_id}:{previous_station_type}")

    # If the order has an assigned driver, also send it to their private room.
    if order.assigned_driver_id:
        rooms.append(f"driver:{order.assigned_driver_id}")

    unique_rooms = set(rooms)
    for room in unique_rooms:
        await socketio_server.emit('order.updated', order_dict, room=room)
    
    logging.debug(f"Broadcasted update for order {order_id} to rooms: {list(unique_rooms)}")


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

    # --- FIX: Broadcast to the specific station's room ---
    # This allows the station UI to listen for updates to its own machines.
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