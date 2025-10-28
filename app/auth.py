# app/auth.py
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlmodel import Session, select

from app.config import JWT_SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.db import get_session
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hashed one."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hashes a password."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# This middleware is ONLY for the web app's cookie-based authentication.
async def set_user_on_request_state(request: Request, session: Session):
    """
    [WEB APP ONLY] Reads the token from cookies, decodes it, and sets `request.state.user`.
    """
    user = None
    token_with_bearer = request.cookies.get("access_token")

    if token_with_bearer and token_with_bearer.startswith("Bearer "):
        token = token_with_bearer.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username:
                user = session.exec(select(User).where(User.username == username)).first()
        except JWTError:
            user = None
    
    request.state.user = user

# This dependency is ONLY for the web app.
def get_current_user(request: Request) -> Optional[User]:
    """[WEB APP ONLY] Returns the user object from the request's state."""
    return getattr(request.state, "user", None)

# --- THIS IS THE FIX ---
# This is the NEW BULLETPROOF DEPENDENCY FOR THE MOBILE APP API
def get_current_api_user(
    request: Request,
    session: Session = Depends(get_session)
) -> User:
    """
    A self-contained dependency for API endpoints (mobile app).
    1. Extracts token from Authorization header.
    2. Decodes token.
    3. Fetches user from DB.
    4. Raises 401/403 if any step fails.
    This avoids any conflicts with request.state or web-based auth.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated: Missing or invalid Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ")[1]
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:
        raise credentials_exception
    
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account is inactive.")
        
    return user


# The dependencies below are used by web app routes that require authentication
async def get_current_active_user(request: Request, current_user: User = Depends(get_current_user)) -> User:
    """[WEB APP ONLY] Dependency to get an active user and redirect if not found."""
    if not current_user:
        next_url = request.url.path
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT, 
            detail="Not authenticated", 
            headers={"Location": f"/login?next={next_url}"}
        )
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account is inactive.")
    return current_user

def get_current_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    if current_user.role != "admin": raise HTTPException(status_code=403, detail="Not an admin")
    return current_user

def get_current_api_admin_user(current_user: User = Depends(get_current_api_user)) -> User:
    """API version of admin user dependency that uses Bearer token auth instead of cookies."""
    if current_user.role != "admin": raise HTTPException(status_code=403, detail="Not an admin")
    return current_user

def get_current_hybrid_admin_user(
    request: Request,
    session: Session = Depends(get_session)
) -> User:
    """
    Hybrid authentication that works for both web app (cookies) and mobile/API clients (Bearer tokens).
    Tries Bearer token first, then falls back to cookie-based auth.
    """
    # Try Bearer token auth first (for API clients)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username:
                user = session.exec(select(User).where(User.username == username)).first()
                if user and user.is_active and user.role == "admin":
                    return user
        except JWTError:
            pass  # Fall through to cookie auth

    # Fall back to cookie-based auth (for web app)
    # Check cookies directly since middleware skips API routes
    token_with_bearer = request.cookies.get("access_token")
    if token_with_bearer and token_with_bearer.startswith("Bearer "):
        token = token_with_bearer.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username:
                user = session.exec(select(User).where(User.username == username)).first()
                if user and user.is_active and user.role == "admin":
                    return user
        except JWTError:
            pass

    # If neither worked, raise unauthorized
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

def get_current_api_driver_user(current_user: User = Depends(get_current_api_user)) -> User:
    """API version of driver user dependency that uses Bearer token auth instead of cookies."""
    if current_user.role != "driver": raise HTTPException(status_code=403, detail="Access denied.")
    return current_user

# Hybrid authentication for web app + mobile app compatibility
def get_current_hybrid_driver_user(
    request: Request,
    session: Session = Depends(get_session)
) -> User:
    """
    Hybrid authentication that works for both web app (cookies) and mobile app (Bearer tokens).
    Tries Bearer token first, then falls back to cookie-based auth.
    """
    # Try Bearer token auth first (for mobile apps)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            if username:
                user = session.exec(select(User).where(User.username == username)).first()
                if user and user.is_active and user.role == "driver":
                    return user
        except JWTError:
            pass  # Fall through to cookie auth

    # Fall back to cookie-based auth (for web app)
    user = getattr(request.state, "user", None)
    if user and user.is_active and user.role == "driver":
        return user

    # If neither worked, raise unauthorized
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

def get_current_staff_user(current_user: User = Depends(get_current_active_user)) -> User:
    if current_user.role not in ["staff", "admin"]: raise HTTPException(status_code=403, detail="Access denied.")
    return current_user

def get_current_driver_user(current_user: User = Depends(get_current_active_user)) -> User:
    if current_user.role != "driver": raise HTTPException(status_code=403, detail="Access denied.")
    return current_user

def get_current_customer_user(current_user: User = Depends(get_current_active_user)) -> User:
    if current_user.role != 'customer': raise HTTPException(status_code=403, detail="Access denied.")
    return current_user

def station_access_dependency(station_name: str):
    def _check_station_access(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role == 'admin': return current_user
        if current_user.role == 'staff':
            if station_name in (current_user.allowed_stations or ""): return current_user
        raise HTTPException(status_code=403, detail=f"Permission denied for {station_name} station.")
    return _check_station_access