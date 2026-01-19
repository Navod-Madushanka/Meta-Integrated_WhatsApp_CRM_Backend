import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# 1. Setup Hashing and Encryption
# .encode() ensures the string key from .env is treated as bytes
fernet = Fernet(settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Hasher:
    """Handles password hashing and verification."""
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        return pwd_context.hash(password)

# 2. Meta Token Encryption Utilities (Step 7 Requirement)
def encrypt_token(token: str) -> str:
    """
    Encrypts Meta Access Tokens using AES-256 before database storage.
    Ensures that sensitive credentials are never stored in plain text.
    """
    if not token:
        return None
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    """
    Decrypts AES-256 encrypted tokens for backend API calls to Meta.
    """
    if not encrypted_token:
        return None
    return fernet.decrypt(encrypted_token.encode()).decode()

# 3. JWT Token Logic for Multi-tenancy
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Generates a JWT for authenticated sessions.
    Encodes the 'sub' (email) and 'business_id' to maintain multi-tenancy.
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.SECRET_KEY, 
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    """Decodes and validates the JWT, returning the payload if valid."""
    try:
        payload = jwt.decode(
            token, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        return payload
    except JWTError:
        logging.error("Could not validate JWT token")
        return None