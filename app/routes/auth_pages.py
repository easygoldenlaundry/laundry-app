# app/routes/auth_pages.py
from datetime import timedelta
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.db import get_session
from app.models import User, Customer
from app.auth import create_access_token, verify_password, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter(tags=["Authentication"])
templates = Jinja2Templates(directory="app/templates")

def wants_json(request: Request) -> bool:
    """Check if the client's Accept header prefers a JSON response."""
    accept_header = request.headers.get("accept", "")
    return "application/json" in accept_header

@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    """Serves the main login page."""
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/api/auth/token")
async def login_for_access_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    next_url: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    """
    Handles form submission from login page/API.
    - For mobile, it returns a JSON object with token and user data.
    - For web, it returns a redirect response with a cookie.
    """
    is_json_request = wants_json(request)

    user = session.exec(select(User).where((User.username == form_data.username) | (User.email == form_data.username))).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        if is_json_request:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password.")
        return templates.TemplateResponse("login.html", {"request": request, "error": "Incorrect username or password."}, status_code=401)
    
    if not user.is_active:
        if is_json_request:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account is inactive.")
        return templates.TemplateResponse("login.html", {"request": request, "error": "Your account is inactive. Please contact an administrator."}, status_code=403)

    access_token = create_access_token(data={"sub": user.username})
    
    if is_json_request:
        customer = session.exec(select(Customer).where(Customer.user_id == user.id)).first()
        return JSONResponse(content={
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id, "name": user.display_name, "email": user.email,
                "phone": customer.phone_number if customer else None,
                "whatsapp": customer.whatsapp_number if customer else None,
                "address": customer.address if customer else None,
                "role": user.role
            }
        })

    # Web-based redirect flow
    default_redirects = {"admin": "/admin/dashboard", "driver": "/driver", "staff": "/hub_intake", "customer": "/account"}
    redirect_url = next_url if next_url and next_url.startswith("/") else default_redirects.get(user.role, "/login")
    
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True, samesite="lax")
    return response

@router.get("/logout")
async def logout(request: Request):
    """Logs the user out by clearing the auth cookie."""
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("access_token")
    return response