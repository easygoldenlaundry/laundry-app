# app/routes/auth_pages.py
from datetime import timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.db import get_session
from app.models import User
from app.auth import create_access_token, verify_password, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(tags=["Authentication"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    """Serves the main login page."""
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/api/auth/token")
async def login_for_access_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    # --- THIS IS THE FIX: Receive the optional 'next_url' from the form ---
    next_url: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    """
    Handles form submission from the login page.
    Redirects to the 'next_url' if provided, otherwise uses role-based default.
    """
    user = session.exec(
        select(User).where((User.username == form_data.username) | (User.email == form_data.username))
    ).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Incorrect username or password."
        }, status_code=401)
    
    if not user.is_active:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Your account is inactive. Please contact an administrator."
        }, status_code=403)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    # --- THIS IS THE FIX: Prioritize the 'next_url' for redirection ---
    # Default role-based redirects
    default_redirects = {
        "admin": "/admin/dashboard",
        "driver": "/driver",
        "staff": "/hub_intake",
        "customer": "/account"
    }
    # Use the next_url if it's a safe, local path. Otherwise, use the role default.
    redirect_url = default_redirects.get(user.role, "/login")
    if next_url and next_url.startswith("/"):
        redirect_url = next_url
    
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        key="access_token", 
        value=f"Bearer {access_token}", 
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/logout")
async def logout(request: Request):
    """Logs the user out by clearing the auth cookie."""
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response