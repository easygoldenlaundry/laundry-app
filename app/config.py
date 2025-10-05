# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

# --- App Constants ---
DATA_ROOT = "./data"

# --- Secrets ---
# Used for signing session cookies (JWTs)
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "b31c43dbab6c17888aaf123f26f0b1f8a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6")
# Used for signing other data, like pending booking cookies
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "zotgmvfgdrleoddqmevqowatadhjnjukyrxyypenjqnzzwdscndlewqanvzdfewuetljsiktthoyelzikdzbkfumxskmphtkbojmmiiqucyrvukogbsmjvcwtyblobrpntivctytncwiwesicdsyicmyrhnxqyjp")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440 # 24 hours