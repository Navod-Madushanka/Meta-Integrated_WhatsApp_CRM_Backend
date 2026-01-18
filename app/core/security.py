from cryptography.fernet import Fernet
from passlib.context import CryptContext
from app.core.config import settings

fernet = Fernet(settings.ENCRYPTION_KEY)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def encrypt_token(token: str) -> str:
    """Encrypts Meta Access Tokens using AES-256."""
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(token: str) -> str:
    """Decrypts AES-256 encrypted tokens."""
    return fernet.decrypt(token.encode()).decode()

class Hasher:
    @staticmethod
    def verify_password(plain, hashed):
        return pwd_context.verify(plain, hashed)

    @staticmethod
    def get_password_hash(password):
        return pwd_context.hash(password)