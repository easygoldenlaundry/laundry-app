# app/routes/auth_pages.py
from datetime import timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from pydantic import BaseModel

from app.db import get_session
from app.models import User, Customer
from app.auth import create_access_token, verify_password, ACCESS_TOKEN_EXPIRE_MINUTES
from app.routes.users import UserProfile, TokenResponse


router = APIRouter(tags=["Authentication"])
templates = Jinja2Templates(directory="app/templates")

def wants_json(request: Request) -> bool:
    """Check if the client's Accept header prefers a JSON response."""
    accept_header = request.headers.get("accept", "")
    return "application/json" in accept_header

@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    """Serves the main login page."""
    # Check for success message in URL parameters
    success_message = request.query_params.get("message")
    if success_message:
        # URL decode the message (replace + with spaces)
        success_message = success_message.replace("+", " ")

    return templates.TemplateResponse("login.html", {
        "request": request,
        "success": success_message
    })

@router.post("/api/auth/token")
async def login_for_access_token_web(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    next_url: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    """
    Handles form submission from the WEB APP ONLY.
    It returns a redirect response with a cookie.
    """
    user = session.exec(select(User).where((User.username == form_data.username) | (User.email == form_data.username))).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Incorrect username or password."}, status_code=401)
    
    if not user.is_active:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Your account is inactive. Please contact an administrator."}, status_code=403)

    access_token = create_access_token(data={"sub": user.username})
    
    default_redirects = {"admin": "/admin/dashboard", "driver": "/driver", "staff": "/hub_intake", "customer": "/account"}
    redirect_url = next_url if next_url and next_url.startswith("/") else default_redirects.get(user.role, "/login")
    
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, samesite="lax")
    return response

# --- THIS IS THE FIX ---
class MobileLoginRequest(BaseModel):
    username: str
    password: str

@router.post("/api/auth/token/mobile", response_model=TokenResponse)
async def login_for_access_token_mobile(
    request_data: MobileLoginRequest,
    session: Session = Depends(get_session)
):
    """
    Handles JSON-based login for MOBILE APP ONLY.
    Returns a JSON object with the token and user data.
    """
    user = session.exec(select(User).where((User.username == request_data.username) | (User.email == request_data.username))).first()

    if not user or not verify_password(request_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password.")
    
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account is inactive.")

    access_token = create_access_token(data={"sub": user.username})
    
    customer = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
    user_profile_data = {
        "id": user.id,
        "name": user.display_name,
        "email": user.email,
        "phone": customer.phone_number if customer else None,
        "whatsapp": customer.whatsapp_number if customer else None,
        "address": customer.address if customer else None,
        "latitude": customer.latitude if customer else None,
        "longitude": customer.longitude if customer else None,
        "staysoft_preference": customer.staysoft_preference if customer else None,
        "additional_notes": customer.additional_notes if customer else None,
        "role": user.role,
        "created_at": user.created_at
    }
    
    return TokenResponse(access_token=access_token, user=UserProfile(**user_profile_data))


@router.get("/logout")
async def logout(request: Request):
    """Logs the user out by clearing the auth cookie."""
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response