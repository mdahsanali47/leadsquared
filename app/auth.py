# app/auth.py
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

# Load environment variables from .env file for local development
load_dotenv()

# --- Configuration ---
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

# --- Hardcoded user data (for this simple app) ---
# In a real app, this would come from a database.
TEST_USERNAME = os.getenv("APP_USERNAME")
TEST_PASSWORD_HASH = os.getenv("APP_PASSWORD_HASH")

if not all([SECRET_KEY, TEST_USERNAME, TEST_PASSWORD_HASH]):
    raise RuntimeError("Missing critical environment variables: SECRET_KEY, APP_USERNAME, APP_PASSWORD_HASH")

# Password Hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# This is a dummy scheme for dependency injection, we will handle the token from cookies.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Functions ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hashed one."""
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Creates a new JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Dummy dependency for getting user from token.
    In main.py, we will create a dependency that reads from cookies instead.
    This function is primarily here to establish the pattern.
    """
    # This will be replaced by a cookie-reading dependency in main.py
    # but we define it here for structure.
    return {"username": token}