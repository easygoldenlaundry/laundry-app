# app/security.py
from itsdangerous import Signer
from app.config import ADMIN_SECRET

# Create the signer here so it can be imported by other modules
# without creating circular dependencies.
signer = Signer(ADMIN_SECRET)