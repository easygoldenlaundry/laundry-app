# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

# --- App Constants ---
DATA_ROOT = "./data"

# --- Environment Detection ---
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
IS_PRODUCTION = ENVIRONMENT == "production"

# --- Database Configuration ---
# Optimized for Supabase connection limits and mobile app usage
if IS_PRODUCTION:
    # Production settings - conservative for Supabase Session mode
    # Supabase Session mode has strict connection limits
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "1"))  # Very conservative
    DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "2"))  # Total max: 3 connections
    DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))  # Longer timeout
    DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "900"))  # 15 minutes - shorter recycle
    DB_POOL_RESET_ON_RETURN = "commit"  # Reset connections on return
else:
    # Development settings - more permissive
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "3"))
    DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "5"))
    DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # 1 hour
    DB_POOL_RESET_ON_RETURN = "commit"

# --- Secrets ---
# Used for signing session cookies (JWTs)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "b31c43dbab6c17888aaf123f26f0b1f8a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6")
# Used for signing other data, like pending booking cookies
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "zotgmvfgdrleoddqmevqowatadhjnjukyrxyypenjqnzzwdscndlewqanvzdfewuetljsiktthoyelzikdzbkfumxskmphtkbojmmiiqucyrvukogbsmjvcwtyblobrpntivctytncwiwesicdsyicmyrhnxqyjp")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 # 24 hours