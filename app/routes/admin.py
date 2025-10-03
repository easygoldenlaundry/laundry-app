# app/routes/admin.py
from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

from app.db import get_session
from app.models import Claim
from app.auth import get_current_admin_user

# The prefix here ensures all routes in this file start with /admin
router = APIRouter(prefix="/admin", dependencies=[Depends(get_current_admin_user)])
templates = Jinja2Templates(directory="app/templates")

@router.get("/uber-dispatch", response_class=HTMLResponse)
async def get_uber_dispatch_page(request: Request):
    """Serves the manual Uber dispatch management page."""
    return templates.TemplateResponse("admin/uber_dispatch.html", {"request": request})

@router.get("/users", response_class=HTMLResponse)
async def get_user_management_page(request: Request):
    """Serves the user management page."""
    return templates.TemplateResponse("admin/users.html", {"request": request})

@router.get("/dashboard", response_class=HTMLResponse)
async def get_admin_dashboard(request: Request):
    """Serves the main admin dashboard page."""
    return templates.TemplateResponse("admin/dashboard.html", {"request": request})

@router.get("/settings", response_class=HTMLResponse)
async def get_settings_page(request: Request):
    """Serves the new settings page."""
    return templates.TemplateResponse("admin/settings.html", {"request": request})

@router.get("/claims", response_class=HTMLResponse)
async def get_claims_management(request: Request, session: Session = Depends(get_session)):
    """Serves the claims management page, fetching all claims."""
    claims = session.exec(
        select(Claim).options(selectinload(Claim.order)).order_by(Claim.created_at.desc())
    ).all()
    return templates.TemplateResponse("admin/claims.html", {"request": request, "claims": claims})