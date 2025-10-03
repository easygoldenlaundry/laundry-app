# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

# --- App Constants ---
DB_PATH = "./brain.db"
DATA_ROOT = "./data"

# --- Secrets ---
# Used for signing session cookies (JWTs)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "a_very_secret_key_that_you_should_change")
# Add the missing secret used by app/security.py
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "another_super_secret_key_for_admins")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 # 24 hours