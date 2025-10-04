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

async def set_user_on_request_state(request: Request, session: Session):
    """
    Reads the token from the Authorization header (for mobile) or cookies (for web),
    decodes it, and sets `request.state.user`.
    """
    user = None
    token_with_bearer = None

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token_with_bearer = auth_header
    if not token_with_bearer:
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

def get_current_user(request: Request) -> Optional[User]:
    """
    FastAPI dependency that returns the user object from the request state.
    """
    return getattr(request.state, "user", None)

# --- THIS IS THE FIX ---
def get_current_active_user(current_user: User = Depends(get_current_user)) -> User:
    """
    Synchronous dependency to get an active user.
    Raises 401 for API if not authenticated or 403 if inactive.
    This is safer for endpoints that also parse request bodies like Forms.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your account is inactive.")
    return current_user
# --- END OF FIX ---

def get_current_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    """Dependency to ensure the user is an active admin."""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an admin")
    return current_user

def get_current_staff_user(current_user: User = Depends(get_current_active_user)) -> User:
    """Dependency to ensure the user is an active staff member or admin."""
    if current_user.role not in ["staff", "admin"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. This page is for hub staff only.")
    return current_user

def get_current_driver_user(current_user: User = Depends(get_current_active_user)) -> User:
    """Dependency to ensure the user is an active driver."""
    if current_user.role != "driver":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. This page is for drivers only.")
    return current_user

def get_current_customer_user(current_user: User = Depends(get_current_active_user)) -> User:
    """Dependency to ensure the user is an active customer."""
    if not current_user or current_user.role != 'customer':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. This action is for customers only."
        )
    return current_user

def station_access_dependency(station_name: str):
    """
    A dependency factory that creates a dependency to check for station access.
    """
    def _check_station_access(current_user: User = Depends(get_current_active_user)) -> User:
        if current_user.role == 'admin':
            return current_user
        if current_user.role == 'staff':
            allowed = (current_user.allowed_stations or "").split(',')
            if station_name in allowed:
                return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not have permission to access the {station_name} station."
        )
    return _check_station_access