import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

# Get key from .env 
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
fernet = Fernet(ENCRYPTION_KEY)

def encrypt_token(token: str) -> str:
    """Encrypts the Meta Access Token before DB storage."""
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    """Decrypts the token for use in API calls."""
    return fernet.decrypt(encrypted_token.encode()).decode()