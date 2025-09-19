# app/routes/health.py
from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter()

@router.get("/health")
def get_health():
    """Returns the current status and time of the server."""
    return {
        "status": "ok",
        "time": datetime.now(timezone.utc).isoformat()
    }