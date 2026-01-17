import os
from cryptography.fernet import Fernet
from passlib.context import CryptContext
from dotenv import load_dotenv

load_dotenv()

# Setup encryption for Meta Tokens
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
fernet = Fernet(ENCRYPTION_KEY)

# Setup password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def encrypt_token(token: str) -> str:
    """Encrypts a string using AES-256 via Fernet."""
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(token: str) -> str:
    """Decrypts an AES-256 encrypted string."""
    return fernet.decrypt(token.encode()).decode()

class Hasher:
    @staticmethod
    def verify_password(plain_password, hashed_password):
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password):
        return pwd_context.hash(password)